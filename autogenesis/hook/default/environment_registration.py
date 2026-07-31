"""EnvironmentRegistrationHook — registers a generated environment class after done_tool fires."""

import os
from typing import Optional

from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.logger import logger
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class EnvironmentRegistrationHook(Hook):
    """Thin wrapper: resolves the environment file path from agent reasoning, then delegates to environment_manager."""

    name: str = "environment_registration_hook"
    description: str = "Registers a generated environment class with environment_manager after generation/optimization."
    priority: int = 10

    async def handle(self, ctx: HookContext) -> HookResult:
        """Locate the generated environment ``.py`` file, promote it if staged, and register it.

        Fired after an environment generation/optimization run calls ``done_tool``.
        Resolves the environment file, validates and promotes it out of any staged
        extension root, then registers it as an evolvable component with
        ``environment_manager`` via ``extension_manager``.

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

        py_path = self._resolve_environment_path(target_name, reasoning, extension_root)
        if not py_path:
            msg = f"Could not locate generated environment file for '{target_name}' in reasoning."
            logger.warning(f"| ⚠️  EnvironmentRegistrationHook: {msg}")
            return HookResult.block(
                f"[registration failed] {msg}\nInclude the file path (extension/<version>/environment/<name>.py) in done_tool reasoning and call done_tool again."
            )

        from autogenesis.sandbox.project import is_staged_extension_root, validate_staged_extension
        if is_staged_extension_root(extension_root):
            validate_staged_extension(extension_root)
            from autogenesis.hook.promotion import promote_approved_component
            py_path = promote_approved_component(extension_root, py_path)

        try:
            from autogenesis.extension import extension_manager
            inferred_name = await extension_manager.add_component("environment", py_path, config={"enable_evolving": True})
            logger.info(f"| 🔄 EnvironmentRegistrationHook: '{inferred_name}' promoted and registered from {py_path}")
        except Exception as e:
            logger.warning(f"| ⚠️  EnvironmentRegistrationHook: {e}")
            return HookResult.block(f"[registration failed] {e}\nPlease fix the file and call done_tool again.")

        return HookResult.allow()

    def _resolve_environment_path(self, target_name: Optional[str], reasoning: str, extension_root: str) -> Optional[str]:
        """Find the generated environment ``.py`` file referenced by the run.

        Prefers an ``extension/.../environment/*.py`` path mentioned in the
        agent's reasoning; falls back to the staged path from ``target_name``.

        Returns:
            The existing environment file path, or ``None`` if none resolves.
        """
        from autogenesis.extension import extension_manager
        # An environment is a *directory-type* component: the loader expects the
        # package directory and reads its fixed `environment.py` entry itself. So
        # resolve to the directory, whether the agent named the directory or the
        # entry file inside it (the creator skill says either is acceptable).
        def _as_package_dir(path: str) -> Optional[str]:
            path = path.rstrip("/")
            if path.endswith(".py"):
                path = os.path.dirname(path)
            return path if os.path.isfile(os.path.join(path, "environment.py")) else None

        for token in reasoning.split():
            token = token.strip(".,;:()")
            if "extension/" not in token or "/environment/" not in token:
                continue
            candidate = token if token.startswith("/") else os.path.join(extension_root, token.removeprefix("extension/"))
            resolved = _as_package_dir(candidate)
            if resolved:
                return resolved
        if target_name:
            resolved = _as_package_dir(extension_manager.stage_path("environment", target_name))
            if resolved:
                return resolved
        return None
