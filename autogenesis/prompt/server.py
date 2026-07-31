"""Prompt Manager

Thin wrapper over PromptContextManager with version management.
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.utils import assemble_workspace_path
from autogenesis.logger import logger
from autogenesis.prompt.types import PromptConfig, Prompt, PromptContext
from autogenesis.prompt.context import PromptContextManager
from autogenesis.response.types import Response


class PromptManagerServer(BaseModel):
    """Prompt Manager for managing prompt registration and lifecycle."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None)

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._registered_configs: Dict[str, PromptConfig] = {}
        # Context manager is created lazily; _ensure_context_manager() initializes it on first use.
        self.prompt_context_manager: Optional[PromptContextManager] = None

    async def _ensure_context_manager(self) -> PromptContextManager:
        """Lazily build and initialize the context manager so methods work before an explicit initialize()."""
        if getattr(self, "prompt_context_manager", None) is None:
            await self.initialize()
        return self.prompt_context_manager

    async def initialize(self, prompt_names: Optional[List[str]] = None):
        """Initialize prompts from md directory.

        Args:
            prompt_names: List of prompt names (md frontmatter `name:`) to load.
                          If None, all md files are loaded.
        """
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "prompt"))
        logger.info(f"| 📁 Prompt Manager base_dir={self.base_dir}")

        self.prompt_context_manager = PromptContextManager(
            base_dir=self.base_dir,
        )
        await self.prompt_context_manager.initialize(prompt_names=prompt_names)
        logger.info("| ✅ Prompts initialization completed")

    async def register(self, prompt: Dict[str, Any], *, override: bool = False) -> PromptConfig:
        cm = await self._ensure_context_manager()
        cfg = await cm.register(prompt, override=override)
        self._registered_configs[cfg.name] = cfg
        return cfg

    async def list(self) -> List[str]:
        cm = await self._ensure_context_manager()
        return await cm.list()

    async def get(self, prompt_name: str) -> Optional[Prompt]:
        cm = await self._ensure_context_manager()
        return await cm.get(prompt_name)

    async def get_info(self, prompt_name: str) -> Optional[PromptConfig]:
        cm = await self._ensure_context_manager()
        return await cm.get_info(prompt_name)

    async def cleanup(self):
        if getattr(self, "prompt_context_manager", None) is not None:
            await self.prompt_context_manager.cleanup()
        self._registered_configs.clear()

    async def update(self, prompt_name: str, prompt: Dict[str, Any],
                     new_version: Optional[str] = None, description: Optional[str] = None) -> PromptConfig:
        cm = await self._ensure_context_manager()
        cfg = await cm.update(prompt_name, prompt,
                              new_version=new_version,
                              description=description)
        self._registered_configs[cfg.name] = cfg
        return cfg

    async def copy(self, prompt_name: str, new_name: Optional[str] = None,
                   new_version: Optional[str] = None, **override_config) -> PromptConfig:
        cm = await self._ensure_context_manager()
        cfg = await cm.copy(prompt_name, new_name, new_version, **override_config)
        self._registered_configs[cfg.name] = cfg
        return cfg

    async def unregister(self, prompt_name: str) -> bool:
        cm = await self._ensure_context_manager()
        success = await cm.unregister(prompt_name)
        if success:
            self._registered_configs.pop(prompt_name, None)
        return success

    async def restore(self, prompt_name: str, version: str, auto_initialize: bool = True) -> Optional[PromptConfig]:
        cm = await self._ensure_context_manager()
        cfg = await cm.restore(prompt_name, version, auto_initialize)
        if cfg:
            self._registered_configs[cfg.name] = cfg
        return cfg

    async def get_system_message(self, prompt_name: str,
                                  modules: Dict[str, Any] = None,
                                  reload: bool = False, **kwargs):
        cm = await self._ensure_context_manager()
        return await cm.get_system_message(
            prompt_name=prompt_name, modules=modules, reload=reload, **kwargs)

    async def get_agent_message(self, prompt_name: str,
                                 modules: Dict[str, Any] = None,
                                 reload: bool = True, **kwargs):
        cm = await self._ensure_context_manager()
        return await cm.get_agent_message(
            prompt_name=prompt_name, modules=modules, reload=reload, **kwargs)

    async def __call__(self, name: str,
                       input: Dict[str, Any] = None,
                       ctx: PromptContext = None,
                       **kwargs) -> Response:
        """Render a prompt's system + agent messages.

        Args:
            name: Prompt name.
            input: Render payload — ``{"system_modules": {...}, "agent_modules": {...}}``.
            ctx: Optional prompt context.

        Returns a Response whose data carries both rendered messages:
            data = {"system_message": ..., "agent_message": ..., "messages": [system, agent]}
        """
        cm = await self._ensure_context_manager()
        return await cm(name, input=input, ctx=ctx, **kwargs)


# Global Prompt Manager instance
prompt_manager = PromptManagerServer()
