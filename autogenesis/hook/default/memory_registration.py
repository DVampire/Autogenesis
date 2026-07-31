"""MemoryRegistrationHook — registers a generated memory system after done_tool fires."""

import os
from typing import Optional

from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.logger import logger
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class MemoryRegistrationHook(Hook):
    """Thin wrapper: resolves the memory file path from agent reasoning, then delegates to memory_manager."""

    name: str = "memory_registration_hook"
    description: str = "Registers a generated memory system with memory_manager after generation/optimization."
    priority: int = 10

    async def handle(self, ctx: HookContext) -> HookResult:
        """Locate the generated memory ``.py`` file, promote it if staged, and register it.

        Fired after a memory generation/optimization run calls ``done_tool``.
        Resolves the memory file, validates and promotes it out of any staged
        extension root, then registers it as an evolvable component with
        ``memory_manager`` via ``extension_manager``.

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

        py_path = self._resolve_memory_path(target_name, reasoning, extension_root)
        if not py_path:
            msg = f"Could not locate generated memory file for '{target_name}' in reasoning."
            logger.warning(f"| ⚠️  MemoryRegistrationHook: {msg}")
            return HookResult.block(
                f"[registration failed] {msg}\nInclude the file path (extension/memory/<name>.py) in done_tool reasoning and call done_tool again."
            )

        from autogenesis.sandbox.project import is_staged_extension_root, validate_staged_extension
        if is_staged_extension_root(extension_root):
            validate_staged_extension(extension_root)
            from autogenesis.hook.promotion import promote_approved_component
            py_path = promote_approved_component(extension_root, py_path)

        try:
            from autogenesis.extension import extension_manager
            inferred_name = await extension_manager.add_component(
                "memory", py_path, config={"enable_evolving": True}
            )
            logger.info(f"| 🔄 MemoryRegistrationHook: '{inferred_name}' promoted and registered from {py_path}")
        except Exception as e:
            logger.warning(f"| ⚠️  MemoryRegistrationHook: {e}")
            return HookResult.block(f"[registration failed] {e}\nPlease fix the file and call done_tool again.")

        return HookResult.allow()

    def _resolve_memory_path(self, target_name: Optional[str], reasoning: str, extension_root: str) -> Optional[str]:
        """Find the generated memory ``.py`` file referenced by the run.

        A memory system is a single-file component (like tool and agent), so the
        path resolves to the ``.py`` itself rather than a package directory.

        Returns:
            The existing memory file path, or ``None`` if nothing resolves.
        """
        from autogenesis.extension import extension_manager
        for token in reasoning.split():
            token = token.strip(".,;:()")
            if "extension/" in token and "/memory/" in token and token.endswith(".py"):
                candidate = token if token.startswith("/") else os.path.join(extension_root, token.removeprefix("extension/"))
                if os.path.isfile(candidate):
                    return candidate
        if target_name:
            path = extension_manager.stage_path("memory", f"{target_name}.py")
            return path if os.path.isfile(path) else None
        return None
