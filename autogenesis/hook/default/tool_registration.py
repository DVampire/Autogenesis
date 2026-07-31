"""ToolRegistrationHook — registers a generated tool file after done_tool fires."""

import os
from typing import Optional

from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.logger import logger
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class ToolRegistrationHook(Hook):
    """Thin wrapper: resolves the tool file path from agent reasoning, then delegates to tool_manager.register()."""

    name: str = "tool_registration_hook"
    description: str = "Registers a generated tool class with tool_manager after generation."
    priority: int = 10

    async def handle(self, ctx: HookContext) -> HookResult:
        """Locate the generated tool ``.py`` file, promote it if staged, and register it.

        Fired after a tool-generating run calls ``done_tool``. Resolves the tool
        file, validates and promotes it out of any staged extension root, then
        registers it as an evolvable component with ``extension_manager``.

        Args:
            ctx: Hook context whose ``input`` carries ``target_name``,
                ``reasoning`` and ``extension_root``.

        Returns:
            ``HookResult.allow()`` on success, or ``HookResult.block(reason)``
            when the file cannot be located or registration fails.
        """
        extra = ctx.input or {}
        target_name: Optional[str] = extra.get("target_name")
        reasoning: str = extra.get("reasoning") or ""
        extension_root: str = extra.get("extension_root") or ""

        tool_path = self._resolve_tool_path(target_name, reasoning, extension_root)
        if not tool_path:
            msg = f"Could not locate generated tool file for '{target_name}' in reasoning."
            logger.warning(f"| ⚠️  ToolRegistrationHook: {msg}")
            return HookResult.block(f"[registration failed] {msg}\nInclude the file path in done_tool reasoning and call done_tool again.")

        from autogenesis.sandbox.project import is_staged_extension_root, validate_staged_extension
        if is_staged_extension_root(extension_root):
            validate_staged_extension(extension_root)
            from autogenesis.hook.promotion import promote_approved_component
            tool_path = promote_approved_component(extension_root, tool_path)

        try:
            from autogenesis.extension import extension_manager
            # Newly generated components are registered evolvable so a later round can optimize
            # them. Overwriting an existing *frozen* entity is still refused inside add_component.
            name = await extension_manager.add_component("tool", tool_path, config={"enable_evolving": True})
            logger.info(f"| 🔄 ToolRegistrationHook: '{name}' promoted and registered from {tool_path}")
            return HookResult.allow()
        except Exception as e:
            logger.warning(f"| ⚠️  ToolRegistrationHook: {e}")
            return HookResult.block(f"[registration failed] {e}\nPlease fix the code and call done_tool again.")

    def _resolve_tool_path(self, target_name: Optional[str], reasoning: str, extension_root: str) -> Optional[str]:
        """Find the generated tool ``.py`` file referenced by the run.

        Prefers an ``extension/.../tool/*.py`` path mentioned in the agent's
        reasoning; falls back to the staged path from ``target_name``.

        Returns:
            The existing tool file path, or ``None`` if none resolves.
        """
        from autogenesis.extension import extension_manager
        for token in reasoning.split():
            token = token.strip(".,;:()")
            if "extension/" in token and "/tool/" in token and token.endswith(".py"):
                candidate = token if token.startswith("/") else os.path.join(extension_root, token.removeprefix("extension/"))
                if os.path.exists(candidate):
                    return candidate
        if target_name:
            path = extension_manager.stage_path("tool", f"{target_name}.py")
            return path if os.path.exists(path) else None
        return None
