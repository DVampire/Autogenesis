"""IDE manager: one VS Code container per gateway session.

Lifecycle is lazy and self-cleaning. A container is started the first time a
client opens the Code view, kept alive by heartbeats while that view is on
screen, and reaped once it has been idle — the gateway has no
``session.close``, so time, not session teardown, is what frees these.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Dict, Optional

from autogenesis.paths import P, path_manager
from autogenesis.ide.types import IdeInstance
from autogenesis.logger import logger
from autogenesis.sandbox.types import SandboxConfig

#: Container paths the entrypoint reads. Mirrored in docker/vscode/.
CONTAINER_WORKSPACE = "/workspace"
CONTAINER_EXTENSIONS = "/ide/extensions"
CONTAINER_USER_DATA = "/ide/user-data"
#: $HOME inside the image (empty there, so mounting over it shadows nothing).
#: The coding agents keep their credentials in it — ~/.codex, ~/.claude — so
#: without a mount every `codex login` would be lost the next time the container
#: is reaped.
CONTAINER_HOME = "/home/workspace"


def base_path(session_id: str) -> str:
    """Sub-path the session's IDE is served under, on the UI's own origin.

    openvscode-server is started with this as ``--server-base-path``, so the
    absolute asset URLs it emits already carry the prefix and the UI can host
    the editor at ``<whatever origin the browser used>/ide/<session>/``. That
    origin is the one thing every deployment agrees on — a per-session
    ``*.ide.localhost`` host, which this used to rely on, is resolved by the
    BROWSER, so it only ever worked when the browser ran on the server itself.
    """
    return f"/ide/{session_id}"


class IdeManagerServer:
    """Start, track, and reap per-session VS Code containers."""

    #: Reap a container after this long with no heartbeat or proxied request.
    idle_timeout_seconds: float = 1800.0
    #: How often the reaper wakes up.
    reap_interval_seconds: float = 60.0
    #: Container self-destruct deadline. Deliberately far beyond the idle
    #: timeout so this manager, not opensandbox, decides when an IDE dies; the
    #: sandbox ledger still reaps it if the gateway crashes.
    container_timeout_minutes: int = 480
    #: Cap concurrent IDEs (each costs ~300-500MB). Starting one past the cap
    #: evicts the least recently used.
    max_instances: int = 4
    #: How long to wait for openvscode-server to accept connections. Generous
    #: because the very first container for an owner installs the default
    #: extensions (a few hundred MB) before the server binds; every later
    #: session finds them already on the mount and comes up in seconds.
    ready_timeout_seconds: float = 600.0

    def __init__(self) -> None:
        self._instances: Dict[str, IdeInstance] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._reaper: Optional[asyncio.Task] = None

    # ----------------------------------------------------------- lifecycle
    async def start(
        self,
        session_id: str,
        *,
        workspace_root: str | Path,
        owner: str = "local",
    ) -> IdeInstance:
        """Return the running IDE for ``session_id``, starting one if needed.

        Extensions, settings and $HOME are mounted from the owner's durable state
        (see the layout table), so installed plugins and agent logins outlive any
        single session even though the container itself is per-session.
        """
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            existing = self._instances.get(session_id)
            if existing is not None:
                existing.last_seen = time.time()
                return existing

            await self._evict_if_full()

            workspace = Path(workspace_root).expanduser().resolve()
            extensions = path_manager.get(P.IDE_EXTENSIONS, owner=owner)
            # Editor state — open tabs, layout, per-workspace history — belongs
            # to the session, so reopening one finds the files it left open
            # rather than another session's. Extensions and the agent logins
            # beside them stay owner-wide: those are worth installing once.
            user_data = path_manager.get(P.SESSION_IDE_USER_DATA, owner=owner, session_id=session_id)
            home = path_manager.get(P.IDE_HOME, owner=owner)
            for directory in (workspace, extensions, user_data, home):
                directory.mkdir(parents=True, exist_ok=True)

            from autogenesis.sandbox.default.vscode import VscodeSandbox

            sandbox = VscodeSandbox(SandboxConfig(
                timeout_minutes=self.container_timeout_minutes,
                # Extensions install from the Open VSX registry over the network.
                network=True,
                env={**self._agent_credentials(), "IDE_BASE_PATH": base_path(session_id)},
                mounts={
                    str(workspace): CONTAINER_WORKSPACE,
                    str(extensions): CONTAINER_EXTENSIONS,
                    str(user_data): CONTAINER_USER_DATA,
                    str(home): CONTAINER_HOME,
                },
            ))
            logger.info(f"| 🟢 IDE starting for session {session_id} ({workspace})")
            await sandbox.start()
            upstream = await sandbox.code_url()

            instance = IdeInstance(
                session_id=session_id, owner=owner, upstream=upstream,
                base_path=base_path(session_id),
                workspace_root=str(workspace), sandbox=sandbox,
            )
            self._instances[session_id] = instance
            self._ensure_reaper()

            if not await self._wait_ready(upstream + instance.base_path):
                logger.warning(f"| ⚠️ IDE for {session_id} did not answer in time; serving anyway")
            logger.info(f"| ✅ IDE ready for session {session_id}")
            return instance

    async def stop(self, session_id: str) -> bool:
        """Destroy the session's IDE container. True if one was running."""
        instance = self._instances.pop(session_id, None)
        if instance is None:
            return False
        logger.info(f"| ⚫ IDE stopping for session {session_id}")
        await self._destroy(instance)
        return True

    async def stop_all(self) -> None:
        """Tear every IDE down (gateway shutdown)."""
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
        for session_id in list(self._instances):
            await self.stop(session_id)

    # -------------------------------------------------------------- lookup
    def upstream(self, session_id: str) -> Optional[str]:
        """Proxy target for a session, refreshing its idle clock.

        Called on every proxied request, so an open IDE tab keeps itself alive
        without depending on the frontend heartbeat.
        """
        instance = self._instances.get(session_id)
        if instance is None:
            return None
        instance.last_seen = time.time()
        return instance.upstream

    async def upstream_for_port(self, session_id: str, port: int) -> Optional[str]:
        """Proxy target for an arbitrary port inside the session's container.

        This is the general form of :meth:`upstream` (which is the IDE's own
        port). Anything the user starts in the integrated terminal — a dev
        server, a preview, an OAuth callback listener — becomes reachable at
        ``<port>-<session>.ide.localhost`` without a line of per-tool code.

        Resolution is cached per port: exposing a port is a round trip to
        opensandbox, and one page load can pull dozens of assets through it.
        """
        instance = self._instances.get(session_id)
        if instance is None:
            return None
        instance.last_seen = time.time()
        cached = instance.port_upstreams.get(port)
        if cached is not None:
            return cached
        if instance.sandbox is None:
            return None
        try:
            resolved = await instance.sandbox.port_url(port)
        except Exception as exc:  # noqa: BLE001 — nothing is listening there yet
            logger.warning(f"| ⚠️ IDE port {port} not exposable for {session_id}: {exc}")
            return None
        instance.port_upstreams[port] = resolved
        return resolved

    def touch(self, session_id: str) -> bool:
        """Heartbeat from the frontend. True if an IDE is running."""
        instance = self._instances.get(session_id)
        if instance is None:
            return False
        instance.last_seen = time.time()
        return True

    def status(self, session_id: str) -> dict:
        instance = self._instances.get(session_id)
        return instance.public() if instance else {"session_id": session_id, "running": False}

    # ------------------------------------------------------------ internals
    #: Credentials the bundled coding agents look for. Forwarded from the
    #: gateway's own environment so Claude Code and Codex are signed in instead
    #: of opening to a "No authentication found" panel.
    #: CLAUDE_CODE_OAUTH_TOKEN is the callback-free path: a browser OAuth login
    #: cannot complete in here, because the CLI's redirect_uri is
    #: localhost:<random port> inside this container and the user's browser
    #: resolves that on their own machine. A long-lived token minted elsewhere
    #: (``claude setup-token``) sidesteps the redirect entirely.
    CREDENTIAL_VARS = (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_API_BASE",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "OPENAI_API_KEY", "OPENAI_BASE_URL",
    )

    @classmethod
    def _agent_credentials(cls) -> Dict[str, str]:
        """Pass the host's agent credentials into the container.

        Only variables that are actually set are forwarded. This does put the
        keys inside the container, where the integrated terminal can read them —
        acceptable because it is the user's own key in their own session, and
        the extensions cannot authenticate any other way, but it is the reason
        the container never also gets the Docker socket.
        """
        import os

        return {name: os.environ[name] for name in cls.CREDENTIAL_VARS if os.environ.get(name)}

    async def _wait_ready(self, upstream: str) -> bool:
        """Poll until openvscode-server answers, so the iframe never races it."""
        import aiohttp

        deadline = time.time() + self.ready_timeout_seconds
        async with aiohttp.ClientSession() as session:
            while time.time() < deadline:
                try:
                    async with session.get(f"{upstream}/", timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status < 500:
                            return True
                except Exception:  # noqa: BLE001 — not up yet
                    pass
                await asyncio.sleep(1.0)
        return False

    async def _evict_if_full(self) -> None:
        while len(self._instances) >= self.max_instances:
            oldest = min(self._instances.values(), key=lambda item: item.last_seen)
            logger.info(f"| ♻️ IDE cap reached; evicting least-recently-used session {oldest.session_id}")
            await self.stop(oldest.session_id)

    @staticmethod
    async def _destroy(instance: IdeInstance) -> None:
        """Destroy a container, never letting teardown raise into the caller."""
        try:
            if instance.sandbox is not None:
                await asyncio.wait_for(instance.sandbox.destroy(), timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ IDE teardown failed for {instance.session_id}: {exc}")

    def _ensure_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap_loop(), name="ide-reaper")

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(self.reap_interval_seconds)
            cutoff = time.time() - self.idle_timeout_seconds
            for session_id, instance in list(self._instances.items()):
                if instance.last_seen < cutoff:
                    logger.info(f"| ⏲️ IDE idle past {self.idle_timeout_seconds:.0f}s; reaping {session_id}")
                    await self.stop(session_id)


# Global IDE manager instance
ide_manager = IdeManagerServer()

__all__ = ["IdeManagerServer", "ide_manager"]
