"""Global context manager for all plugins with lazy loading support.

Same shape as :class:`EnvironmentContextManager`: the :data:`PLUGIN` registry
hands over classes, ``_load_from_registry`` turns each into a
:class:`PluginConfig` (class + settings + version + source), and ``build``
instantiates it. A plugin's tools mirror an environment's actions — they come
off the class rather than off a decorator, because each is its own file under
``tools/``.

Plugins wrap third-party services, so the evolution half of the environment
manager (``update`` / ``copy`` / ``restore``) has no counterpart here: rewriting
a vendor's API adapter at runtime is not something the optimizer should do.
Registration, versioning and lifecycle are the same.
"""

import inspect
import os
from typing import Any, Dict, List, Optional, Tuple, Type

import inflection
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.dynamic import dynamic_manager
from autogenesis.logger import logger
from autogenesis.registry import PLUGIN
from autogenesis.response.types import Response, ResponseType
from autogenesis.plugins.types import Plugin, PluginConfig, PluginContext, PluginTool
from autogenesis.utils import assemble_workspace_path, gather_with_concurrency
from autogenesis.version import version_manager


class PluginContextManager(BaseModel):
    """Global context manager for all plugins with lazy loading support."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="The base directory to use for the plugins")

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the plugin context manager.

        Args:
            base_dir: Base directory for storing plugin data
        """
        super().__init__(**kwargs)

        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            base_root = config.log_root if hasattr(config, "log_root") and config.get("log_root") else config.workspace_root
            self.base_dir = assemble_workspace_path(os.path.join(base_root, "plugin"))
        logger.info(f"| 📁 Plugin context manager base directory: {self.base_dir}.")

        self._plugin_configs: Dict[str, PluginConfig] = {}
        # Plugin version history, e.g. {"tavily": {"1.0.0": PluginConfig}}
        self._plugin_history_versions: Dict[str, Dict[str, PluginConfig]] = {}

    async def initialize(self, plugin_names: Optional[List[str]] = None):
        """Initialize the plugin context manager.

        Args:
            plugin_names: Plugins to build. None builds every registered plugin.
        """
        await version_manager.initialize()

        plugin_configs: Dict[str, PluginConfig] = await self._load_from_registry()

        wanted = plugin_configs if plugin_names is None else {
            name: cfg for name, cfg in plugin_configs.items() if name in plugin_names
        }
        for plugin_config in wanted.values():
            try:
                await self.build(plugin_config)
            except Exception as e:  # noqa: BLE001 — one bad plugin must not abort startup
                logger.error(f"| ❌ Failed to build plugin {plugin_config.name}: {e}")

        tool_count = sum(len(cfg.tools) for cfg in self._plugin_configs.values())
        logger.info(f"| ✅ Plugins initialization completed "
                    f"({len(self._plugin_configs)} plugins, {tool_count} tools)")

    async def _load_from_registry(self) -> Dict[str, PluginConfig]:
        """Load plugins from the PLUGIN registry."""
        plugin_configs: Dict[str, PluginConfig] = {}

        async def register_plugin_class(plugin_cls: Type[Plugin]):
            """Turn one registered class into a PluginConfig."""
            try:
                plugin_config_key = inflection.underscore(plugin_cls.__name__)
                plugin_config_dict = config.get(plugin_config_key, {}) or {}
                plugin_enable_evolving = bool(plugin_config_dict.get("enable_evolving", False))

                fields = plugin_cls.model_fields
                plugin_name = fields["name"].default or plugin_config_key
                plugin_display_name = fields["display_name"].default or plugin_name
                plugin_description = fields["description"].default
                plugin_metadata = fields["metadata"].default

                plugin_version = await version_manager.get_version("plugin", plugin_name)
                plugin_code = dynamic_manager.get_full_module_source(plugin_cls)
                try:
                    plugin_path = inspect.getfile(plugin_cls)
                except Exception:  # noqa: BLE001 — dynamically defined classes have no file
                    plugin_path = None

                plugin_config = PluginConfig(
                    name=plugin_name,
                    display_name=plugin_display_name,
                    description=plugin_description,
                    metadata=plugin_metadata,
                    version=plugin_version,
                    enable_evolving=plugin_enable_evolving,
                    cls=plugin_cls,
                    config=plugin_config_dict,
                    instance=None,
                    code=plugin_code,
                    path=plugin_path,
                )

                plugin_configs[plugin_name] = plugin_config

                if plugin_name not in self._plugin_history_versions:
                    self._plugin_history_versions[plugin_name] = {}
                self._plugin_history_versions[plugin_name][plugin_version] = plugin_config

                await version_manager.register_version("plugin", plugin_name, plugin_version)

                logger.info(f"| 📝 Registered plugin: {plugin_name} ({plugin_cls.__name__})")

            except Exception as e:  # noqa: BLE001
                logger.error(f"| ❌ Failed to register plugin class {plugin_cls.__name__}: {e}")
                raise

        plugin_classes = list(PLUGIN._module_dict.values())

        logger.info(f"| 🔍 Discovering {len(plugin_classes)} plugins from PLUGIN registry")

        results = await gather_with_concurrency(
            [register_plugin_class(cls) for cls in plugin_classes],
            max_concurrency=10, return_exceptions=True,
        )
        success_count = sum(1 for r in results if not isinstance(r, Exception))

        logger.info(f"| ✅ Discovered and registered {success_count}/{len(plugin_classes)} "
                    f"plugins from PLUGIN registry")

        return plugin_configs

    async def build(self, plugin_config: PluginConfig) -> PluginConfig:
        """Build a plugin instance from config.

        Args:
            plugin_config: Plugin configuration

        Returns:
            PluginConfig: Plugin configuration with instance and tools
        """
        existing = self._plugin_configs.get(plugin_config.name)
        if existing is not None and existing.instance is not None:
            return existing

        try:
            if plugin_config.cls is None:
                raise ValueError(
                    f"Cannot create plugin {plugin_config.name}: no class provided. "
                    "Class should be loaded during initialization.")

            instance: Plugin = (plugin_config.cls(**plugin_config.config)
                                if plugin_config.config else plugin_config.cls())
            if not instance.name:
                instance.name = plugin_config.name
            await instance.initialize()

            plugin_config.instance = instance
            # The class binds its tools at construction; surface them on the
            # config the way an environment surfaces its actions.
            plugin_config.tools = {tool.name: tool for tool in instance.tool_list()}
            if not plugin_config.tools:
                logger.warning(f"| ⚠️ Plugin {plugin_config.name} declares no tools")

            self._plugin_configs[plugin_config.name] = plugin_config

            logger.info(f"| ✅ Plugin {plugin_config.name} created with "
                        f"{len(plugin_config.tools)} tool(s)")
            return plugin_config
        except Exception as e:  # noqa: BLE001
            logger.error(f"| ❌ Failed to create plugin {plugin_config.name}: {e}")
            raise

    async def register(self, plugin: Plugin, override: bool = False) -> PluginConfig:
        """Register a plugin instance directly (used by tests and extensions)."""
        if plugin.name in self._plugin_configs and not override:
            raise ValueError(f"Plugin '{plugin.name}' already registered. Use override=True.")
        await plugin.initialize()
        plugin_config = PluginConfig(
            name=plugin.name,
            display_name=plugin.display_name or plugin.name,
            description=plugin.description,
            metadata=plugin.metadata,
            version=await version_manager.get_version("plugin", plugin.name),
            cls=type(plugin),
            config={},
            instance=plugin,
            tools={tool.name: tool for tool in plugin.tool_list()},
        )
        self._plugin_configs[plugin.name] = plugin_config
        return plugin_config

    async def unregister(self, plugin_name: str) -> bool:
        """Drop a plugin, cleaning up its instance first. True if one was there."""
        plugin_config = self._plugin_configs.pop(plugin_name, None)
        if plugin_config is None:
            return False
        if plugin_config.instance is not None:
            try:
                await plugin_config.instance.cleanup()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"| ⚠️ Error cleaning up plugin {plugin_name}: {e}")
        self._plugin_history_versions.pop(plugin_name, None)
        return True

    # ---------------------------------------------------------------- lookup
    async def get(self, plugin_name: str) -> Optional[Plugin]:
        """Get a plugin instance by name (accepts a ``<plugin>.<tool>`` address)."""
        plugin_config, _ = self._resolve(plugin_name)
        return plugin_config.instance if plugin_config else None

    async def get_info(self, name: str) -> Optional[Any]:
        """Descriptor for whatever ``name`` addresses: a plugin, or one of its tools."""
        plugin_config, tool_name = self._resolve(name)
        if plugin_config is None:
            return None
        return plugin_config.tools.get(tool_name) if tool_name else plugin_config

    async def list(self) -> List[str]:
        """Registered plugin names."""
        return list(self._plugin_configs.keys())

    async def list_infos(self) -> List[PluginConfig]:
        """Every registered plugin config (for catalog/roster building)."""
        return list(self._plugin_configs.values())

    async def list_tools(self) -> List[PluginTool]:
        """Every tool of every plugin — one canvas node each."""
        return [tool for cfg in self._plugin_configs.values() for tool in cfg.tools.values()]

    def _resolve(self, name: str) -> Tuple[Optional[PluginConfig], str]:
        """Split ``<plugin>.<tool>`` into its config and the tool's short name."""
        plugin_config = self._plugin_configs.get(name)
        if plugin_config is not None:
            return plugin_config, ""
        plugin_name, _, tool_name = name.partition(".")
        return self._plugin_configs.get(plugin_name), tool_name

    # -------------------------------------------------------------- dispatch
    async def __call__(self, name: str, tool: str = "", input: Dict[str, Any] = None,
                       ctx: PluginContext = None, **kwargs) -> Response:
        """Call one of a plugin's tools.

        Args:
            name: Plugin name, or the ``<plugin>.<tool>`` address
            tool: Tool short name, when not already part of ``name``
            input: Input for the tool

        Returns:
            The tool's canonical Response.
        """
        plugin_config, addressed_tool = self._resolve(name)
        if plugin_config is None:
            return Response(type=ResponseType.TOOL, success=False, message=f"Unknown plugin: {name}")
        if plugin_config.instance is None:
            await self.build(plugin_config)

        logger.info(f"| ✅ Using plugin {plugin_config.name}@{plugin_config.version}")
        payload = input or {}
        target = tool or addressed_tool
        # A bare plugin name goes through the plugin's own ``__call__``, so a
        # single-capability plugin can keep a natural signature.
        if target:
            return await plugin_config.instance.invoke(target, **payload)
        return await plugin_config.instance(**payload)

    async def cleanup(self):
        """Cleanup all active plugins."""
        try:
            for plugin_name, plugin_config in self._plugin_configs.items():
                if plugin_config.instance is not None:
                    try:
                        await plugin_config.instance.cleanup()
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"| ⚠️ Error cleaning up plugin {plugin_name} instance: {e}")

            self._plugin_configs.clear()
            self._plugin_history_versions.clear()

            logger.info("| 🧹 Plugin context manager cleaned up")
        except Exception as e:  # noqa: BLE001
            logger.error(f"| ❌ Error during plugin context manager cleanup: {e}")


__all__ = ["PluginContextManager"]
