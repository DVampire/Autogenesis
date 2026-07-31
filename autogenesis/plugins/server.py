"""Plugin Manager Server

Server implementation for plugin management with lazy loading support.
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.plugins.context import PluginContextManager
from autogenesis.plugins.types import Plugin, PluginConfig, PluginContext, PluginTool
from autogenesis.response.types import Response
from autogenesis.utils import assemble_workspace_path


class PluginManagerServer(BaseModel):
    """Plugin manager server for registration and tool invocation."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    base_dir: str = Field(default=None, description="The base directory to use for the plugins")

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the plugin manager server."""
        super().__init__(**kwargs)
        # Created lazily: config may not be loaded at import time. initialize()
        # reconfigures it with the proper base_dir.
        self.plugin_context_manager: Optional[PluginContextManager] = None

    def _ensure_context_manager(self) -> PluginContextManager:
        """Lazily create the context manager so methods work before initialize()."""
        if self.plugin_context_manager is None:
            self.plugin_context_manager = PluginContextManager()
        return self.plugin_context_manager

    async def initialize(self, plugin_names: Optional[List[str]] = None) -> None:
        """Build plugin instances from the PLUGIN registry.

        Args:
            plugin_names: Plugins to build. None builds every registered plugin.
        """
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "plugin"))
        logger.info(f"| 📁 Plugin manager server base directory: {self.base_dir}")

        self.plugin_context_manager = PluginContextManager(base_dir=self.base_dir)
        await self._ensure_context_manager().initialize(plugin_names=plugin_names)

    # ---------------------------------------------------------------- lookup
    async def list(self) -> List[str]:
        """List registered plugin names."""
        return await self._ensure_context_manager().list()

    async def list_infos(self) -> List[PluginConfig]:
        """Every registered plugin config (for catalog/roster building)."""
        return await self._ensure_context_manager().list_infos()

    async def list_tools(self) -> List[PluginTool]:
        """Every tool of every plugin — one canvas node each."""
        return await self._ensure_context_manager().list_tools()

    async def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin instance by name (accepts a ``<plugin>.<tool>`` address)."""
        return await self._ensure_context_manager().get(name)

    async def get_info(self, name: str) -> Optional[Any]:
        """Descriptor for whatever ``name`` addresses: a plugin, or one of its tools."""
        return await self._ensure_context_manager().get_info(name)

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Plugins accept free-form provider params; no strict call schema (yet)."""
        return None

    # -------------------------------------------------------------- lifecycle
    async def register(self, plugin: Plugin, override: bool = False) -> PluginConfig:
        """Register a plugin instance directly (used by tests and extensions)."""
        return await self._ensure_context_manager().register(plugin, override=override)

    async def unregister(self, name: str) -> bool:
        """Drop a plugin. True if one was registered."""
        return await self._ensure_context_manager().unregister(name)

    async def __call__(self, name: str, input: Dict[str, Any] = None,
                       ctx: PluginContext = None, **kwargs) -> Response:
        """Invoke ``<plugin>.<tool>``; failures come back as an unsuccessful Response."""
        return await self._ensure_context_manager()(name, input=input, ctx=ctx, **kwargs)

    async def cleanup(self) -> None:
        """Tear down every plugin's provider resources."""
        await self._ensure_context_manager().cleanup()


# Global plugin manager instance
plugin_manager = PluginManagerServer()

__all__ = ["PluginManagerServer", "plugin_manager"]
