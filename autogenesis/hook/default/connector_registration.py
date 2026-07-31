"""ConnectorRegistrationHook — registers a generated connector directory after done_tool fires."""

import os
from typing import Optional

from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.logger import logger
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class ConnectorRegistrationHook(Hook):
    """Thin wrapper: resolves the connector directory from agent reasoning, then delegates to connector_manager.register()."""

    name: str = "connector_registration_hook"
    description: str = "Registers a generated connector directory (CONNECTOR.md) with connector_manager after generation."
    priority: int = 10

    async def handle(self, ctx: HookContext) -> HookResult:
        """Locate the generated connector directory, promote it if staged, and register it.

        Fired after a connector-generating run calls ``done_tool``. Resolves the
        connector directory (containing ``CONNECTOR.md``), validates and promotes
        it out of any staged extension root, then registers it as an evolvable
        component with ``extension_manager``.

        Args:
            ctx: Hook context whose ``input`` carries ``target_name``,
                ``reasoning`` and ``extension_root``.

        Returns:
            ``HookResult.allow()`` on success, or ``HookResult.block(reason)``
            when the directory cannot be located or registration fails.
        """
        extra = ctx.input or {}
        target_name: Optional[str] = extra.get("target_name")
        reasoning: str = extra.get("reasoning") or ""
        extension_root: str = extra.get("extension_root") or ""

        connector_dir = self._resolve_connector_dir(target_name, reasoning, extension_root)
        if not connector_dir:
            msg = f"Could not locate generated connector directory for '{target_name}' in reasoning."
            logger.warning(f"| ⚠️  ConnectorRegistrationHook: {msg}")
            return HookResult.block(f"[registration failed] {msg}\nInclude the connector directory path in done_tool reasoning and call done_tool again.")

        from autogenesis.sandbox.project import is_staged_extension_root, validate_staged_extension
        if is_staged_extension_root(extension_root):
            validate_staged_extension(extension_root)
            from autogenesis.hook.promotion import promote_approved_component
            connector_dir = promote_approved_component(extension_root, connector_dir)

        try:
            from autogenesis.extension import extension_manager
            # Newly generated components are registered evolvable so a later round can optimize
            # them. Overwriting an existing *frozen* entity is still refused inside add_component.
            name = await extension_manager.add_component("connector", connector_dir, config={"enable_evolving": True})
            logger.info(f"| 🔄 ConnectorRegistrationHook: '{name}' promoted and registered from {connector_dir}")
            return HookResult.allow()
        except Exception as e:
            logger.warning(f"| ⚠️  ConnectorRegistrationHook: {e}")
            return HookResult.block(f"[registration failed] {e}\nPlease fix the issue and call done_tool again.")

    def _resolve_connector_dir(self, target_name: Optional[str], reasoning: str, extension_root: str) -> Optional[str]:
        """Find the generated connector directory referenced by the run.

        Prefers an ``extension/.../connector/...`` path mentioned in the agent's
        reasoning; falls back to the staged directory derived from ``target_name``.

        Returns:
            The existing connector directory path, or ``None`` if none resolves.
        """
        from autogenesis.extension import extension_manager
        for token in reasoning.split():
            if "extension/" in token and "/connector/" in token:
                candidate = token.strip(".,;:()")
                if not candidate.startswith("/"):
                    candidate = os.path.join(extension_root, candidate.removeprefix("extension/"))
                if os.path.isdir(candidate.rstrip("/")):
                    return candidate.rstrip("/")
        if target_name:
            path = extension_manager.stage_path("connector", target_name)
            return path if os.path.isdir(path) else None
        return None
