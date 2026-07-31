"""HookManagerServer — thin server wrapper around HookContextManager.

Parallels AgentManagerServer / autogenesis/agent/server.py.
All logic lives in HookContextManager; this class just owns the singleton
instance and exposes a stable public API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type  # Dict/Any kept for register() signature

from autogenesis.logger import logger
from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.hook.context import HookContextManager, HookConfig


class HookManagerServer:
    """Singleton server for hook registration and dispatch.

    Parallels AgentManagerServer: stores a HookContextManager and delegates
    every method to it.  Call ``await hook_manager.initialize()`` once at
    startup before any hooks are dispatched.
    """

    def __init__(self) -> None:
        self.hook_context_manager: Optional[HookContextManager] = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, hook_names: Optional[List[str]] = None) -> None:
        """Discover and instantiate hooks from the HOOK registry.

        Args:
            hook_names: If provided, only load hooks whose snake_case class
                        name is in this list. None loads all discovered hooks.
        """
        self.hook_context_manager = HookContextManager()
        await self.hook_context_manager.initialize(hook_names=hook_names)
        logger.info("| ✅ Hook manager server initialized")

    def _require_manager(self) -> HookContextManager:
        """Return the underlying manager, raising if the server was never initialized.

        Raises:
            RuntimeError: If ``initialize()`` has not been called yet.
        """
        if self.hook_context_manager is None:
            raise RuntimeError(
                "HookManagerServer has not been initialized. "
                "Call `await hook_manager.initialize()` first."
            )
        return self.hook_context_manager

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(
        self,
        hook_cls: Type[Hook],
        config: Optional[Dict[str, Any]] = None,
    ) -> HookConfig:
        """Register (or replace) a hook class.

        Args:
            hook_cls: Hook subclass to register.
            config:   Optional init kwargs passed to the constructor.

        Returns:
            HookConfig of the newly registered hook.
        """
        return await self._require_manager().register(hook_cls, config=config)

    def unregister(self, name: str) -> None:
        """Remove a hook from the registry by name."""
        self._require_manager().unregister(name)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get(self, name: str) -> Optional[Hook]:
        """Return the live Hook instance registered under ``name``."""
        return await self._require_manager().get(name)

    async def get_info(self, name: str) -> Optional[HookConfig]:
        """Return the HookConfig registered under ``name``."""
        return await self._require_manager().get_info(name)

    def list(self) -> List[str]:
        """Return a list of registered hook names, sorted by priority."""
        if self.hook_context_manager is None:
            return []
        return self.hook_context_manager.list()

    # ------------------------------------------------------------------
    # Dispatch — mirrors AgentManagerServer.__call__
    # ------------------------------------------------------------------

    async def __call__(
        self,
        name: str,
        input: dict,
        ctx=None,
        **kwargs,
    ) -> HookResult:
        """Dispatch to the hook registered under ``name``.

        Args:
            name:  Registered hook name (e.g. ``"memory_hook"``).
            input: Event payload dict. ``"event"`` key is required.
            ctx:   Any context with an ``.id`` attribute.

        Returns:
            HookResult (ALLOW if no hook is registered under ``name``).
        """
        if self.hook_context_manager is None:
            # Graceful no-op before initialization (e.g. during tests)
            return HookResult.allow()
        return await self.hook_context_manager(name, input, ctx=ctx, **kwargs)


# Global singleton — import this everywhere
hook_manager = HookManagerServer()
