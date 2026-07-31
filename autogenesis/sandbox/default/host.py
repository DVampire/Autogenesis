"""HostSandbox — a NON-isolated "sandbox" that runs directly on the host.

This is the fallback backend for when no container runtime (Docker daemon or k8s)
is available, so deployments still work on a plain machine. It implements the same
:class:`~autogenesis.sandbox.types.Sandbox` surface the deployment manager uses
(``run_command`` / ``write_file`` / ``expose_port``) but against the host filesystem
and host processes — there is **no isolation**. A background start command (one ending
in ``&``) is launched in its own process group and tracked so ``destroy`` can kill it.

Use only for dev/demo or trusted single-tenant hosts. For real isolation use the
``opensandbox`` backend (which needs Docker/k8s).
"""

from __future__ import annotations

import os
import signal
import subprocess
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

from autogenesis.logger import logger
from autogenesis.registry import SANDBOX
from autogenesis.sandbox.types import ExecResult, Sandbox, SandboxConfig


@SANDBOX.register_module(name="host", force=True)
class HostSandbox(Sandbox):
    """Run commands/servers directly on the host (no container isolation)."""

    name: str = "host"
    description: str = "Runs services directly on the host — fallback when no container runtime is available (NO isolation)."

    def __init__(self, config: Optional[SandboxConfig] = None, **kwargs: Any):
        super().__init__(config, **kwargs)
        self._procs: List[subprocess.Popen] = []   # tracked background processes
        self._root: str = ""

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._started:
            return
        base = getattr(self.config, "host_base", None) or os.path.join("workspace_root", "deploy_host")
        self._root = os.path.abspath(base)
        os.makedirs(self._root, exist_ok=True)
        self._started = True
        logger.info(f"| 🖥️  HostSandbox started (root={self._root}, NO isolation)")

    async def destroy(self) -> None:
        for p in self._procs:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
        self._procs.clear()
        self._started = False

    # ------------------------------------------------------------- execution
    async def run_command(
        self,
        command: str,
        *,
        workspace_root: Optional[str] = None,
        timeout: Optional[Union[int, timedelta]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        cwd = workspace_root or self._root
        try:
            os.makedirs(cwd, exist_ok=True)
        except Exception:
            pass
        run_env = {**os.environ, **(self.config.env or {}), **(env or {})}

        stripped = command.rstrip()
        if stripped.endswith("&"):
            # Background launch (a server): run it in its own session so the whole
            # process group can be killed later; return immediately.
            bg = stripped[:-1].strip()
            try:
                p = subprocess.Popen(
                    bg, shell=True, cwd=cwd, env=run_env,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._procs.append(p)
                return ExecResult(success=True, stdout=f"launched pid {p.pid}")
            except Exception as e:
                return ExecResult(success=False, error=f"failed to launch: {e}")

        secs = timeout.total_seconds() if isinstance(timeout, timedelta) else timeout
        try:
            r = subprocess.run(
                command, shell=True, cwd=cwd, env=run_env,
                capture_output=True, text=True, timeout=secs,
            )
            return ExecResult(
                success=(r.returncode == 0), stdout=r.stdout or "",
                stderr=r.stderr or "", exit_code=r.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(success=False, error=f"command timed out after {secs}s")
        except Exception as e:
            return ExecResult(success=False, error=f"command failed: {e}")

    # ------------------------------------------------------------- files
    async def write_file(self, path: str, data: Union[str, bytes], *, mode: int = 0o644) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb" if isinstance(data, (bytes, bytearray)) else "w") as fh:
            fh.write(data)
        try:
            os.chmod(path, mode)
        except Exception:
            pass

    async def read_file(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    async def read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as fh:
            return fh.read()

    def launched_alive(self) -> bool:
        """True if a background server was launched and is still running.

        Returns True when nothing has been launched yet (nothing to judge), and False
        only when we started a server that has since exited (e.g. failed to bind a port)
        — the deployment manager uses this so a dead server is not mistaken for "up".
        """
        if not self._procs:
            return True
        return any(p.poll() is None for p in self._procs)

    # ------------------------------------------------------------- network
    async def expose_port(self, port: int) -> str:
        # The server binds a host port directly; it is reachable at localhost on this host.
        return f"http://localhost:{port}"
