"""Prompt Context Manager — md-file-based prompt lifecycle with version management."""

import asyncio
import glob
import os
from asyncio_atexit import register as async_atexit_register
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.version import version_manager
from autogenesis.utils import assemble_workspace_path
from autogenesis.utils.file_utils import file_lock
from autogenesis.prompt.types import Prompt, PromptConfig, PromptContext, parse_prompt_file
from autogenesis.message.types import Message
from autogenesis.response.types import Response, ResponseType
from autogenesis.permission import permission_manager, PermissionMode


class PromptContextManager(BaseModel):
    """Global context manager for all prompts with version management."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None)
    default_prompt_dir: str = Field(default=None, description="Directory for built-in default prompts")
    extension_prompt_dir: str = Field(default=None, description="Directory for generated/user prompts")

    def __init__(self,
                 base_dir: Optional[str] = None,
                 default_prompt_dir: Optional[str] = None,
                 extension_prompt_dir: Optional[str] = None,
                 **kwargs):
        super().__init__(**kwargs)

        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "prompt"))


        _src_dir = Path(__file__).resolve().parent
        # Built-in prompts live in the default/ dir; extension prompts are managed
        # externally (loaded by ExtensionManager into the active version).
        self.default_prompt_dir = default_prompt_dir or str(_src_dir / "default")
        self.extension_prompt_dir = extension_prompt_dir or assemble_workspace_path(os.path.join("extension", "prompt"))

        logger.info(f"| 📁 Prompt context manager base_dir={self.base_dir}")

        self._prompt_configs: Dict[str, PromptConfig] = {}
        self._prompt_history_versions: Dict[str, Dict[str, PromptConfig]] = {}

        self._cleanup_registered = False
        self._variables_lock = asyncio.Lock()

        if not self._cleanup_registered:
            async_atexit_register(self.cleanup)
            self._cleanup_registered = True

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, prompt_names: Optional[List[str]] = None):
        """Load prompts from md directory, then overlay JSON-versioned overrides."""
        Path(self.extension_prompt_dir).mkdir(parents=True, exist_ok=True)

        md_configs = await self._load_from_registry(self.default_prompt_dir)
        extension_configs = await self._load_from_registry(self.extension_prompt_dir)
        md_configs.update(extension_configs)  # extension overrides default on name collision

        json_configs = {}

        merged: Dict[str, PromptConfig] = dict(md_configs)
        for name, json_cfg in json_configs.items():
            if name in merged:
                if version_manager.compare_versions(json_cfg.version, merged[name].version) > 0:
                    logger.info(f"| 🔄 Override {name}: md v{merged[name].version} → json v{json_cfg.version}")
                    merged[name] = json_cfg
                else:
                    logger.info(f"| 📌 Keep md {name} v{merged[name].version} (json v{json_cfg.version} not greater)")
            else:
                merged[name] = json_cfg

        if prompt_names is not None:
            merged = {k: v for k, v in merged.items() if k in prompt_names}

        for name, cfg in merged.items():
            self._prompt_configs[name] = cfg
            if name not in self._prompt_history_versions:
                self._prompt_history_versions[name] = {}
            self._prompt_history_versions[name][cfg.version] = cfg
            await version_manager.register_version("prompt", name, cfg.version)
            permission_manager.register(
                entity_name=name,
                mode=PermissionMode(getattr(cfg, "permission_mode", "workspace_write")),
            )
            logger.info(f"| 🔧 Prompt {name} v{cfg.version} ready")

        logger.info("| ✅ Prompts initialization completed")

    async def _load_from_registry(self, template_dir: str) -> Dict[str, PromptConfig]:
        """Scan template_dir for *.html files and parse each into a PromptConfig."""
        configs: Dict[str, PromptConfig] = {}
        html_files = glob.glob(os.path.join(template_dir, "*.html"))
        logger.info(f"| 🔍 Found {len(html_files)} html files in {template_dir}")

        for path in html_files:
            try:
                cfg = parse_prompt_file(path)
                if not cfg.name:
                    logger.warning(f"| ⚠️ Skipping {path}: missing 'name' in meta")
                    continue
                configs[cfg.name] = cfg
                logger.info(f"| 📝 Loaded prompt '{cfg.name}' from {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"| ❌ Failed to parse {path}: {e}")

        return configs

    async def register(self, prompt: Dict[str, Any], *, override: bool = False) -> PromptConfig:
        """Register a prompt from a dict."""
        cfg = PromptConfig.model_validate(prompt)
        if not cfg.name:
            raise ValueError("Prompt name cannot be empty")
        if cfg.name in self._prompt_configs and not override:
            raise ValueError(f"Prompt '{cfg.name}' already registered. Use override=True.")

        version = await version_manager.get_version("prompt", cfg.name)
        cfg.version = version

        self._prompt_configs[cfg.name] = cfg
        if cfg.name not in self._prompt_history_versions:
            self._prompt_history_versions[cfg.name] = {}
        self._prompt_history_versions[cfg.name][version] = cfg
        await version_manager.register_version("prompt", cfg.name, version)
        return cfg

    async def update(self, prompt_name: str, prompt: Dict[str, Any],
                     new_version: Optional[str] = None,
                     description: Optional[str] = None) -> PromptConfig:
        """Update an existing prompt and create a new version."""
        original = self._prompt_configs.get(prompt_name)
        if original is None:
            raise ValueError(f"Prompt '{prompt_name}' not found. Use register() first.")

        new_cfg = PromptConfig.model_validate({**original.model_dump(), **prompt})
        new_cfg.name = prompt_name

        if new_version is None:
            new_version = await version_manager.generate_next_version("prompt", prompt_name, "patch")
        new_cfg.version = new_version

        self._prompt_configs[prompt_name] = new_cfg
        if prompt_name not in self._prompt_history_versions:
            self._prompt_history_versions[prompt_name] = {}
        self._prompt_history_versions[prompt_name][new_version] = new_cfg
        await version_manager.register_version("prompt", prompt_name, new_version,
                                               description=description or f"Updated from {original.version}")
        logger.info(f"| 📝 Updated prompt {prompt_name} v{new_version}")
        return new_cfg

    async def unregister(self, prompt_name: str) -> bool:
        if prompt_name not in self._prompt_configs:
            logger.warning(f"| ⚠️ Prompt {prompt_name} not found")
            return False
        del self._prompt_configs[prompt_name]
        return True

    async def restore(self, prompt_name: str, version: str, auto_initialize: bool = True) -> Optional[PromptConfig]:
        version_cfg = self._prompt_history_versions.get(prompt_name, {}).get(version)
        if version_cfg is None:
            logger.warning(f"| ⚠️ Version {version} not found for prompt {prompt_name}")
            return None
        restored = PromptConfig.model_validate(version_cfg.model_dump())
        self._prompt_configs[prompt_name] = restored
        logger.info(f"| 🔄 Restored prompt {prompt_name} to v{version}")
        return restored

    async def copy(self, prompt_name: str, new_name: Optional[str] = None,
                   new_version: Optional[str] = None, **override_config) -> PromptConfig:
        original = self._prompt_configs.get(prompt_name)
        if original is None:
            raise ValueError(f"Prompt '{prompt_name}' not found")

        target_name = new_name or prompt_name
        if new_version is None:
            new_version = await version_manager.get_version("prompt", target_name)

        new_data = original.model_dump()
        new_data["name"] = target_name
        new_data["version"] = new_version
        new_data.update({k: v for k, v in override_config.items() if k in new_data})

        new_cfg = PromptConfig.model_validate(new_data)
        self._prompt_configs[target_name] = new_cfg
        if target_name not in self._prompt_history_versions:
            self._prompt_history_versions[target_name] = {}
        self._prompt_history_versions[target_name][new_version] = new_cfg
        await version_manager.register_version("prompt", target_name, new_version,
                                               description=f"Copied from {prompt_name}@{original.version}")
        logger.info(f"| 📋 Copied {prompt_name}@{original.version} → {target_name}@{new_version}")
        return new_cfg

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    async def get(self, name: str) -> Optional[Prompt]:
        cfg = self._prompt_configs.get(name)
        return cfg.to_prompt() if cfg else None

    async def get_info(self, name: str) -> Optional[PromptConfig]:
        return self._prompt_configs.get(name)

    async def list(self) -> List[str]:
        return list(self._prompt_configs.keys())

    # ------------------------------------------------------------------
    # Message rendering
    # ------------------------------------------------------------------

    async def get_system_message(self, prompt_name: str,
                                  modules: Dict[str, Any] = None,
                                  reload: bool = False, **kwargs):
        cfg = self._prompt_configs.get(prompt_name)
        if cfg is None:
            raise ValueError(f"Prompt '{prompt_name}' not found")
        logger.info(f"| ✅ Rendering system message for {prompt_name} v{cfg.version}")
        return await cfg.to_prompt().get_system_message(modules=modules, reload=reload)

    async def get_agent_message(self, prompt_name: str,
                                 modules: Dict[str, Any] = None,
                                 reload: bool = True, **kwargs):
        cfg = self._prompt_configs.get(prompt_name)
        if cfg is None:
            raise ValueError(f"Prompt '{prompt_name}' not found")
        logger.info(f"| ✅ Rendering user message for {prompt_name} v{cfg.version}")
        return await cfg.to_prompt().get_user_message(modules=modules, reload=reload)

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
        input = input or {}
        system_modules = input.get("system_modules")
        agent_modules = input.get("agent_modules")

        cfg = self._prompt_configs.get(name)
        if cfg is None:
            error_msg = f"Prompt '{name}' is not registered. Available prompts: {list(self._prompt_configs.keys())}"
            logger.error(f"| ❌ {error_msg}")
            return Response(type=ResponseType.PROMPT, success=False, message=error_msg)

        system_message = await self.get_system_message(name, system_modules, reload=False)
        agent_message = await self.get_agent_message(name, agent_modules, reload=True)

        logger.info(f"| ✅ Rendered messages for prompt {name} v{cfg.version}")
        return Response(
            type=ResponseType.PROMPT,
            success=True,
            message=f"Rendered messages for prompt {name} v{cfg.version}",
            data={
                "system_message": system_message,
                "agent_message": agent_message,
                "messages": [system_message, agent_message],
            },
        )

    # ------------------------------------------------------------------
    # Trainable variables
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def cleanup(self):
        try:
            self._prompt_configs.clear()
            self._prompt_history_versions.clear()
            logger.info("| 🧹 Prompt context manager cleaned up")
        except Exception as e:
            logger.error(f"| ❌ Error during cleanup: {e}")
