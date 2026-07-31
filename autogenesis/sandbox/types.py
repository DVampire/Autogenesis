"""Sandbox subsystem base types.

A *sandbox* is an isolated execution context (a container) in which the
framework can run shell commands, execute code, read/write files, and expose
network ports — without touching the host. Concrete backends live in
``autogenesis/sandbox/default/`` and register with the ``SANDBOX`` registry.

This module deliberately stays light: a sandbox is infrastructure, not an
evolvable LLM-facing component, so there is no versioning / persistence /
contract machinery here (unlike tools, agents, skills).
"""

from __future__ import annotations

import base64
import shlex
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class SandboxConfig(BaseModel):
    """Construction config for a sandbox handle."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    image: Optional[str] = Field(default=None, description="Container image to launch.")
    entrypoint: Optional[List[str]] = Field(default=None, description="Container entrypoint override.")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables inside the sandbox.")
    timeout_minutes: int = Field(default=10, description="Sandbox lifetime before auto-kill.")
    network: bool = Field(default=True, description="Whether the sandbox has outbound network access.")
    # Host directories bind-mounted into the container, as {host_path: container_path}.
    # Peer sandboxes mount the repo at /Autogenesis so files (source + outputs) are
    # consistent across the base container and its peers — see base.py, which turns each
    # entry into an opensandbox Volume(host=Host(path=...), mount_path=...).
    mounts: Dict[str, str] = Field(default_factory=dict, description="Host->container bind mounts {host_path: container_path}.")
    # opensandbox-server connection. None -> resolved through the port manager
    # (see autogenesis.sandbox.process.default_domain), so the daemon port is
    # de-conflicted rather than hard-coded to 8080.
    domain: Optional[str] = Field(default=None, description="opensandbox-server domain; None resolves via the port manager.")
    api_key: Optional[str] = Field(default=None, description="opensandbox-server API key, if any.")


class ExecResult(BaseModel):
    """Normalized result of running a command or code in a sandbox."""

    success: bool = True
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    results: List[str] = Field(default_factory=list, description="Rich result values (e.g. interpreter return values).")
    error: Optional[str] = None

    def as_message(self) -> str:
        """Human/LLM-readable rendering."""
        parts: List[str] = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.stderr:
            parts.append(f"[stderr]\n{self.stderr.rstrip()}")
        if self.error:
            parts.append(f"[error]\n{self.error.rstrip()}")
        if self.exit_code not in (None, 0):
            parts.append(f"[exit_code] {self.exit_code}")
        return "\n".join(parts) if parts else "(no output)"


class Sandbox:
    """Base class for a sandbox handle (one isolated container).

    Subclasses wrap a concrete backend (OpenSandbox, E2B, Docker, ...) and
    implement the lifecycle + the execution/file/network surface. Handles hold
    live async clients, so this is a plain class (not a pydantic model).

    Lifecycle::

        sb = SomeSandbox(config)
        await sb.start()
        res = await sb.run_command("ls -la")
        await sb.destroy()
    """

    #: Registry name (the string a caller passes to ``sandbox_manager.acquire``).
    name: str = "sandbox"
    description: str = "Base sandbox handle."

    def __init__(self, config: Optional[SandboxConfig] = None, **kwargs: Any):
        self.config = config or SandboxConfig(**kwargs)
        self._started = False

    @property
    def container_workspace(self) -> Optional[str]:
        """Working directory *inside* this sandbox, as seen by commands run in it.

        None means the sandbox runs on host paths directly (no remapping), so the
        prompt keeps showing the host workspace_root. Container-backed sandboxes
        override this so the prompt matches where bash_tool actually runs.
        """
        return None

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Create/connect the underlying container. Idempotent."""
        raise NotImplementedError

    async def destroy(self) -> None:
        """Tear down the underlying container."""
        raise NotImplementedError

    async def is_alive(self) -> bool:
        return self._started

    # ------------------------------------------------------------- execution
    async def run_command(
        self,
        command: str,
        *,
        workspace_root: Optional[str] = None,
        timeout: Optional[Union[int, timedelta]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Run a shell command inside the sandbox."""
        raise NotImplementedError

    async def run_code(
        self,
        code: str,
        *,
        language: str = "python",
    ) -> ExecResult:
        """Execute code via a code-interpreter kernel. Backends without an
        interpreter raise NotImplementedError."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support run_code; code runs in the project kernel "
            f"(autogenesis.kernel), not in a sandbox."
        )

    # ------------------------------------------------------------- files
    # These have default implementations built on ``run_command`` so a backend
    # only has to implement command execution to get a full file surface. Backends
    # with a native file API (LocalSandbox, OpenSandbox) override them for speed;
    # base64 piping avoids shell-quoting pitfalls with arbitrary content.
    async def write_file(self, path: str, data: Union[str, bytes], *, mode: int = 0o644) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        encoded = base64.b64encode(raw).decode("ascii")
        parent = path.rsplit("/", 1)[0] if "/" in path else "."
        cmd = f"mkdir -p {shlex.quote(parent)} && echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}"
        res = await self.run_command(cmd)
        if not res.success or (res.exit_code not in (None, 0)):
            raise IOError(f"write_file({path!r}) failed: {res.as_message()}")

    async def read_file(self, path: str) -> str:
        return (await self.read_bytes(path)).decode("utf-8", errors="replace")

    async def read_bytes(self, path: str) -> bytes:
        res = await self.run_command(f"base64 {shlex.quote(path)}")
        if not res.success or (res.exit_code not in (None, 0)):
            raise IOError(f"read_bytes({path!r}) failed: {res.as_message()}")
        return base64.b64decode(res.stdout.strip())

    # ------------------------------------------------------------- network
    async def expose_port(self, port: int) -> str:
        """Return an externally reachable URL for a port inside the sandbox."""
        raise NotImplementedError

    # ------------------------------------------------------------- context mgr
    async def __aenter__(self) -> "Sandbox":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.destroy()
