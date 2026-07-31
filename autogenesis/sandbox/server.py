"""Sandbox Manager Server.

``sandbox_manager`` is the singleton entry point for the sandbox subsystem.
Unlike the tool/agent/skill managers it carries no versioning/persistence
machinery — a sandbox is infrastructure, not an evolvable component. It:

  * lazily ensures the opensandbox-server daemon is running (via the handles),
  * hands out started :class:`~autogenesis.sandbox.types.Sandbox` handles by *kind*
    (``"opensandbox"``, ``"playwright"``, ``"vscode"``, ...),
  * optionally caches a handle per ``reuse_key`` (e.g. a session id) so callers
    can keep a warm container across calls instead of paying cold-start each time,
  * tears everything down on cleanup.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict

from autogenesis.logger import logger
from autogenesis.registry import SANDBOX
from autogenesis.sandbox.process import shutdown_all
from autogenesis.sandbox.types import Sandbox, SandboxConfig


class SandboxManagerServer(BaseModel):
    """Manages sandbox handles backed by opensandbox."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # reuse_key -> live started handle
        self._handles: Dict[str, Sandbox] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Import built-in sandbox backends so they register. Idempotent."""
        if self._initialized:
            return
        # Trigger @SANDBOX.register_module on the built-in handles.
        import autogenesis.sandbox.default  # noqa: F401
        self._initialized = True
        logger.info(f"| 🧩 Sandbox manager ready (kinds: {await self.list()})")

    # ------------------------------------------------------------- discovery
    async def list(self) -> List[str]:
        await self._ensure_registered()
        return sorted(SANDBOX.module_dict.keys())

    async def get(self, kind: str) -> Type[Sandbox]:
        """Return the registered sandbox *class* for a kind (not a live handle)."""
        await self._ensure_registered()
        cls = SANDBOX.get(kind)
        if cls is None:
            raise ValueError(f"No registered sandbox kind {kind!r}. Available: {await self.list()}")
        return cls

    async def _ensure_registered(self) -> None:
        if not self._initialized:
            await self.initialize()

    # ------------------------------------------------------------- handles
    async def acquire(
        self,
        kind: str = "opensandbox",
        *,
        reuse_key: Optional[str] = None,
        start: bool = True,
        **config: Any,
    ) -> Sandbox:
        """Create (or reuse) a started sandbox handle of the given kind.

        Args:
            kind: registered sandbox kind (``opensandbox`` / ``playwright`` / ``vscode``).
            reuse_key: if given, the handle is cached and reused for this key
                (e.g. a session id) so the container stays warm across calls.
            start: whether to ``await handle.start()`` before returning.
            **config: overrides forwarded to :class:`SandboxConfig`
                (image, env, timeout_minutes, domain, api_key, ...).
        """
        cache_key = f"{kind}:{reuse_key}" if reuse_key else None
        if cache_key and cache_key in self._handles:
            handle = self._handles[cache_key]
            if await handle.is_alive():
                return handle
            self._handles.pop(cache_key, None)

        cls = await self.get(kind)
        handle = cls(SandboxConfig(**config))
        if start:
            await handle.start()
        if cache_key:
            self._handles[cache_key] = handle
        return handle

    async def release(self, kind: str = "opensandbox", *, reuse_key: Optional[str] = None) -> None:
        """Destroy a cached handle for a reuse_key."""
        cache_key = f"{kind}:{reuse_key}" if reuse_key else None
        if cache_key and cache_key in self._handles:
            handle = self._handles.pop(cache_key)
            await handle.destroy()

    async def cleanup(self) -> None:
        """Destroy all cached handles and stop the opensandbox-server daemon."""
        for handle in list(self._handles.values()):
            try:
                await handle.destroy()
            except Exception as e:
                logger.warning(f"| ⚠️ Error destroying sandbox handle: {e}")
        self._handles.clear()
        await shutdown_all()


# Global sandbox manager instance
sandbox_manager = SandboxManagerServer()
