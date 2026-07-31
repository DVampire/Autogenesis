"""Hook Context Manager — hook registry, initialization, and dispatch.

Parallels AgentContextManager from autogenesis/agent/context.py.

Each hook is stateless by design: any per-session state lives inside the
hook instance itself (via PrivateAttr), not in a shared session store.
"""

from __future__ import annotations

import inflection
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.hook.types import Hook, HookContext, HookDecision, HookEvent, HookResult, check_message_contract


def _contract_mode() -> str:
    """Resolve hook contract mode: env > config.hook_contract_mode > 'warn'."""
    import os
    env = os.environ.get("AUTOGENESIS_CONTRACT_MODE")
    if env:
        return env.strip().lower()
    try:
        from autogenesis.config import config
        return str(getattr(config, "hook_contract_mode", "warn")).lower()
    except Exception:
        return "warn"


# ---------------------------------------------------------------------------
# HookConfig — per-hook configuration (parallel to AgentConfig)
# ---------------------------------------------------------------------------

class HookConfig(BaseModel):
    """Configuration record for a registered hook."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Unique hook name.")
    description: str = Field(default="", description="What this hook does.")
    enabled: bool = Field(default=True)
    priority: int = Field(default=100, description="Execution priority — lower runs first.")

    cls: Optional[Any] = Field(default=None, description="Hook class.")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Init config dict.")
    instance: Optional[Any] = Field(default=None, description="Live hook instance.")

    def __str__(self) -> str:
        return f"HookConfig(name={self.name}, enabled={self.enabled}, priority={self.priority})"

    def __repr__(self) -> str:
        return self.__str__()


# ---------------------------------------------------------------------------
# HookContextManager — hook registry + dispatch (parallel to AgentContextManager)
# ---------------------------------------------------------------------------

class HookContextManager:
    """Global context manager for all hooks — registry, initialization, and dispatch.

    Parallels AgentContextManager from autogenesis/agent/context.py.
    Hook dispatch is by registered name (exact match), mirroring how
    AgentContextManager dispatches by agent name.

    Hooks are stateless by design. Any per-session state a hook needs lives
    inside the hook instance itself (e.g. via pydantic PrivateAttr), not here.
    """

    def __init__(self) -> None:
        # name → HookConfig (current registered hooks)
        self._hook_configs: Dict[str, HookConfig] = {}

    # ------------------------------------------------------------------
    # Initialization — auto-discover from HOOK registry
    # ------------------------------------------------------------------

    async def initialize(self, hook_names: Optional[List[str]] = None) -> None:
        """Discover all @HOOK.register_module classes, instantiate them, and register.

        Args:
            hook_names: If provided, only register hooks whose snake_case class name
                        is in this list. None means register all discovered hooks.
        """
        hook_configs = await self._load_from_registry(hook_names=hook_names)

        for hook_config in hook_configs.values():
            try:
                built_config = await self.build(hook_config)
                self._hook_configs[built_config.name] = built_config
                logger.info(f"| 🎣 Hook '{built_config.name}' initialized")
            except Exception as e:
                logger.error(f"| ❌ Failed to initialize hook '{hook_config.name}': {e}")

        logger.info(f"| ✅ Hooks initialization completed: {self.list()}")

    async def _load_from_registry(
        self, hook_names: Optional[List[str]] = None
    ) -> Dict[str, HookConfig]:
        """Load hook classes from the HOOK registry and build HookConfig objects."""
        import autogenesis.hook  # ensure all default hooks are imported/registered
        from autogenesis.registry import HOOK
        from autogenesis.config import config

        hook_classes: List[Type[Hook]] = list(HOOK._module_dict.values())
        logger.info(f"| 🔍 Discovering {len(hook_classes)} hooks from HOOK registry")

        hook_configs: Dict[str, HookConfig] = {}

        for hook_cls in hook_classes:
            key = inflection.underscore(hook_cls.__name__)
            if hook_names is not None and key not in hook_names:
                continue
            hook_cfg_dict: dict = getattr(config, key, {}) or {}

            try:
                fields = hook_cls.model_fields
                default_name     = fields["name"].default     if "name"     in fields else key
                default_desc     = fields["description"].default if "description" in fields else ""
                default_priority = fields["priority"].default  if "priority" in fields else 100
                default_enabled  = fields["enabled"].default   if "enabled"  in fields else True

                hook_config = HookConfig(
                    name=hook_cfg_dict.get("name", default_name),
                    description=hook_cfg_dict.get("description", default_desc),
                    enabled=hook_cfg_dict.get("enabled", default_enabled),
                    priority=hook_cfg_dict.get("priority", default_priority),
                    cls=hook_cls,
                    config=hook_cfg_dict,
                    instance=None,
                )
                hook_configs[hook_config.name] = hook_config
                logger.info(f"| 📝 Discovered hook: {hook_config.name} ({hook_cls.__name__})")
            except Exception as e:
                logger.error(f"| ❌ Failed to build config for hook {hook_cls.__name__}: {e}")

        return hook_configs

    # ------------------------------------------------------------------
    # Build — instantiate a hook from its config
    # ------------------------------------------------------------------

    async def build(self, hook_config: HookConfig) -> HookConfig:
        """Instantiate a hook from its HookConfig and store the live instance."""
        if hook_config.name in self._hook_configs:
            existing = self._hook_configs[hook_config.name]
            if existing.instance is not None:
                return existing

        if hook_config.cls is None:
            raise ValueError(f"Cannot create hook '{hook_config.name}': no class provided.")

        cfg = hook_config.config or {}
        try:
            instance: Hook = hook_config.cls(**cfg) if cfg else hook_config.cls()
        except Exception as e:
            logger.error(f"| ❌ Failed to instantiate hook '{hook_config.name}': {e}")
            raise

        hook_config.instance = instance
        self._hook_configs[hook_config.name] = hook_config
        logger.info(f"| 🔧 Hook '{hook_config.name}' created (priority={instance.priority})")
        return hook_config

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(
        self,
        hook_cls: Type[Hook],
        config: Optional[Dict[str, Any]] = None,
    ) -> HookConfig:
        """Register (or replace) a hook class, instantiate it, and store."""
        cfg = config or {}
        try:
            instance: Hook = hook_cls(**cfg) if cfg else hook_cls()
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate hook {hook_cls.__name__} with config {cfg}: {e}"
            ) from e

        hook_config = HookConfig(
            name=instance.name,
            description=instance.description,
            enabled=instance.enabled,
            priority=instance.priority,
            cls=hook_cls,
            config=cfg,
            instance=instance,
        )
        self._hook_configs[hook_config.name] = hook_config
        logger.info(f"| 🔌 Hook registered: {hook_config.name} (priority={hook_config.priority})")
        return hook_config

    def unregister(self, name: str) -> None:
        """Remove a hook from the registry."""
        if name in self._hook_configs:
            del self._hook_configs[name]
            logger.info(f"| 🗑️ Hook unregistered: {name}")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get(self, name: str) -> Optional[Hook]:
        """Return the live hook instance, or None if not found."""
        cfg = self._hook_configs.get(name)
        return cfg.instance if cfg else None

    async def get_info(self, name: str) -> Optional[HookConfig]:
        """Return the HookConfig for a registered hook."""
        return self._hook_configs.get(name)

    def list(self) -> List[str]:
        """Return names of all registered hooks, sorted by priority."""
        return [
            name
            for name, _ in sorted(
                self._hook_configs.items(), key=lambda kv: kv[1].priority
            )
        ]

    # ------------------------------------------------------------------
    # Dispatch — parallel to AgentContextManager.__call__
    # ------------------------------------------------------------------

    async def __call__(
        self,
        name: str,
        input: Dict[str, Any],
        ctx=None,
        **kwargs,
    ) -> HookResult:
        """Dispatch to the hook registered under ``name``.

        Routing is by hook name (exact match), mirroring how AgentContextManager
        routes by agent name.

        Args:
            name:  Registered hook name to invoke (e.g. ``"memory_hook"``).
            input: Event payload dict. ``"event"`` key is required.
            ctx:   Any context with an ``.id`` attribute (AgentContext, etc.).

        Returns a HookResult. Hooks that raise are logged and treated as ALLOW.
        """
        event = input.get("event")
        if event is None:
            raise ValueError("'event' is required in input")
        session_id = ctx.id if ctx is not None else ""
        hook_ctx = HookContext(
            id=session_id,
            name=name,
            input=input,
        )

        hook_config = self._hook_configs.get(name)
        if hook_config is None or not hook_config.enabled or hook_config.instance is None:
            return HookResult.allow()

        hook_instance = hook_config.instance

        try:
            result = await hook_instance.handle(hook_ctx)
        except Exception as e:
            logger.warning(f"| ⚠️ Hook '{name}' raised on {event}: {e}")
            result = HookResult.allow()

        # Contract-as-code: validate a MODIFY hook's rewritten messages. In strict
        # mode a violation propagates (caught by no one here — surfaces to the run
        # loop); in warn mode it only logs. Off skips entirely.
        if result.decision == HookDecision.MODIFY and result.modified_messages is not None:
            check_message_contract(result.modified_messages, mode=_contract_mode(), hook_name=name)

        if result.additional_context:
            logger.debug(
                f"| 💬 Hook '{name}' additional_context injected "
                f"({len(result.additional_context)} chars)"
            )

        # ON_STOP: let the hook release its own per-session resources
        if event == HookEvent.ON_STOP:
            try:
                await hook_instance.cleanup(hook_ctx.id)
            except Exception as e:
                logger.debug(f"| Hook '{name}' cleanup raised: {e}")

        return result
