"""OpenSandbox server-process lifecycle.

A single ``opensandbox-server`` daemon backs every sandbox in the application.
This module owns starting/health-checking/stopping that daemon. It has no
dependency on the registry or the manager, so both the manager and individual
sandbox handles can import it without a cycle.

Moved here from the old ``autogenesis/environment/sandbox.py`` (now removed) so the
sandbox subsystem owns its own server process.
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
from typing import Optional

import httpx

from autogenesis.logger import logger
from pathlib import Path


def _host_repo_root() -> str:
    """The repo root as the HOST sees it — the bind-mount allowlist prefix.

    Inside the repo container the tree is at /Autogenesis, but the daemon binds
    mounts against the host's filesystem, so the allowlist has to name the host
    path. ``scripts/run-in-sandbox.sh`` exports it; running directly on the host
    the local repo root is already correct.
    """
    host_root = os.environ.get("AUTOGENESIS_HOST_ROOT")
    if host_root:
        return host_root
    # .../autogenesis/sandbox/process.py -> repo root
    return str(Path(__file__).resolve().parents[2])


class SandboxServerManager:
    """Manages the lifecycle of a local opensandbox-server process.

    Usage::

        mgr = SandboxServerManager(domain=default_domain())
        await mgr.ensure_running()   # idempotent — starts the daemon if needed
        ...
        await mgr.shutdown()         # once, on global cleanup
    """

    def __init__(
        self,
        domain: str,
        server_bin: str = "opensandbox-server",
        startup_timeout: float = 30.0,
        poll_interval: float = 0.5,
    ):
        self.domain = domain
        self.server_bin = server_bin
        self.startup_timeout = startup_timeout
        self.poll_interval = poll_interval
        self._process: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------------ public
    async def ensure_running(self) -> None:
        """Start the server if it is not already reachable. Idempotent."""
        if await self.is_healthy():
            logger.info(f"| 📦 opensandbox-server already running at {self.domain}")
            return
        await self._start()
        await self._wait_until_ready()

    async def shutdown(self) -> None:
        """Terminate the server process if we started it."""
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=10)
            logger.info("| 🛑 opensandbox-server stopped")
        except Exception as e:
            logger.warning(f"| ⚠️ Error stopping opensandbox-server: {e}")
            self._process.kill()
        finally:
            self._process = None

    async def is_healthy(self) -> bool:
        url = f"http://{self.domain}/healthz"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                return resp.status_code < 500
        except Exception:
            return False

    # ----------------------------------------------------------------- private
    def _write_config(self) -> None:
        """Write ~/.sandbox.toml before starting the server.

        Drops security options (drop_capabilities, no_new_privileges, pids_limit)
        blocked by restrictive Docker authz plugins on some hosts. Also points
        [server].port at self.domain's port — otherwise the spawned process keeps
        listening on whatever port was last written (8080 by default) regardless of
        the domain a caller passed to steer the client elsewhere, so a caller using a
        non-default domain (e.g. because 8080 is already occupied by an unrelated
        service on a shared host) would silently get a server on the wrong port and
        time out waiting for it to become "ready" at the domain it actually polls.
        """
        config_path = os.path.expanduser("~/.sandbox.toml")
        try:
            with open(config_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            bin_path = shutil.which(self.server_bin) or os.path.join(
                os.path.dirname(sys.executable), self.server_bin
            )
            subprocess.run(
                [bin_path, "init-config", config_path, "--example", "docker"],
                check=True, capture_output=True,
            )
            with open(config_path, "r") as f:
                content = f.read()

        def _replace_or_append(text: str, key: str, new_value: str) -> str:
            pattern = rf"^({re.escape(key)}\s*=\s*).*$"
            replacement = f"{key} = {new_value}"
            new_text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
            if count == 0:
                new_text = re.sub(r"(\[docker\])", rf"\1\n{replacement}", new_text, count=1)
            return new_text

        content = _replace_or_append(content, "drop_capabilities", "[]")
        content = _replace_or_append(content, "no_new_privileges", "false")
        content = re.sub(r"^pids_limit\s*=.*\n?", "", content, flags=re.MULTILINE)

        # Bind mounts are refused unless their source sits under an allowed
        # prefix, and the shipped default is an empty list — which denies every
        # path despite the config comment claiming empty means "allow all".
        # Permit exactly the repo tree, since that is where every mount we make
        # lives (session workspaces and durable state, both under output/).
        content = _replace_or_append(
            content, "allowed_host_paths", f'["{_host_repo_root()}"]'
        )

        port = self.domain.rsplit(":", 1)[-1]
        if port.isdigit():
            content = _replace_or_append(content, "port", port)

        with open(config_path, "w") as f:
            f.write(content)
        logger.info(f"| 🔧 opensandbox-server config written to {config_path}")

    async def _start(self) -> None:
        bin_path = shutil.which(self.server_bin)
        if bin_path is None:
            candidate = os.path.join(os.path.dirname(sys.executable), self.server_bin)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                bin_path = candidate
        if bin_path is None:
            raise RuntimeError(
                f"opensandbox-server binary not found (looked for '{self.server_bin}'). "
                "Install it with: pip install opensandbox-server"
            )

        self._write_config()
        env = os.environ.copy()
        env.setdefault("OPENSANDBOX_INSECURE_SERVER", "YES")
        logger.info(f"| 🚀 Starting opensandbox-server ({bin_path})")
        self._process = subprocess.Popen(
            [bin_path], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    async def _wait_until_ready(self) -> None:
        elapsed = 0.0
        while elapsed < self.startup_timeout:
            if await self.is_healthy():
                logger.info(f"| ✅ opensandbox-server ready at {self.domain} (took {elapsed:.1f}s)")
                return
            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval
        raise TimeoutError(
            f"opensandbox-server did not become ready within {self.startup_timeout}s"
        )


# A single shared daemon for the whole process. ``ensure_server`` is safe to
# call from anywhere (manager, handles, environments).
_server_singletons: dict = {}
_default_domain: Optional[str] = None


def default_domain() -> str:
    """Resolve the daemon's domain through the port manager, once per process.

    The port is reserved via ``port_manager`` (preferring the well-known
    ``OPENSANDBOX`` port, falling back to any free port when it is taken) so the
    sandbox daemon never hard-codes 8080 and never collides with another service
    on a shared host. Cached process-wide: every sandbox shares one daemon on one
    managed port.
    """
    global _default_domain
    if _default_domain is None:
        from autogenesis.port import port_manager, OPENSANDBOX
        rec = port_manager.register("opensandbox", preferred=OPENSANDBOX, type="host")
        _default_domain = f"localhost:{rec['port']}"
    return _default_domain


_stale_sandboxes_reaped = False


async def ensure_server(domain: Optional[str] = None, server_bin: str = "opensandbox-server") -> SandboxServerManager:
    # Before this process creates its first sandbox, remove containers a dead
    # previous run left behind — orphans otherwise break subsequent creates
    # (observed with leaked chrome-vnc peers killing browser-environment init).
    global _stale_sandboxes_reaped
    if not _stale_sandboxes_reaped:
        _stale_sandboxes_reaped = True
        try:
            from autogenesis.sandbox.ledger import ledger
            await ledger.reap_stale()
        except Exception as e:  # noqa: BLE001 — reaping is best-effort
            logger.warning(f"| ⚠️ Could not reap stale sandboxes: {e}")

    domain = domain or default_domain()
    mgr = _server_singletons.get(domain)
    if mgr is None:
        mgr = SandboxServerManager(domain=domain, server_bin=server_bin)
        _server_singletons[domain] = mgr
    await mgr.ensure_running()
    return mgr


async def shutdown_all() -> None:
    for mgr in list(_server_singletons.values()):
        await mgr.shutdown()
    _server_singletons.clear()
