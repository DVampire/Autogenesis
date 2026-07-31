"""Tool Manager Server

Server implementation for tool management with lazy loading support.
"""
from typing import Any, Dict, List, Optional, Tuple, Type, Union
import os
from pydantic import BaseModel, ConfigDict, Field


from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.tool.context import ToolContextManager
from autogenesis.tool.types import Tool, ToolConfig, ToolContext
from autogenesis.response.types import Response
from autogenesis.utils import assemble_workspace_path
from autogenesis.capability import CapabilitySchema, SchemaSource

class ToolManagerServer(BaseModel):
    """tool manager Server for managing tool registration and execution with lazy loading."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    base_dir: str = Field(default=None, description="The base directory to use for the tools")
    
    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the tool manager Server."""
        super().__init__(**kwargs)
        self._registered_configs: Dict[str, ToolConfig] = {}  # tool_name -> ToolConfig
        # Context manager is created lazily (config may not be loaded at import time).
        # initialize() reconfigures it with proper base_dir .
        self.tool_context_manager: Optional[ToolContextManager] = None
        
    def _ensure_context_manager(self) -> ToolContextManager:
        """Lazily create the context manager so methods work before initialize() is called."""
        if self.tool_context_manager is None:
            self.tool_context_manager = ToolContextManager()
        return self.tool_context_manager

    async def initialize(self, tool_names: Optional[List[str]] = None):
        """Initialize tools by names using tool context manager with concurrent support.
        
        Args:
            tool_names: List of tool names to initialize. If None, initialize all registered tools.
        """
        
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "tool"))
        logger.info(f"| 📁 tool manager Server base directory: {self.base_dir}")
        
        # Initialize tool context manager
        self.tool_context_manager = ToolContextManager(
            base_dir=self.base_dir,
            model_name="openrouter/gemini-3-flash-preview",
        )
        await self._ensure_context_manager().initialize(tool_names=tool_names)
        
        logger.info("| ✅ Tools initialization completed")
        
    async def get_instruction(self, allowlist: Optional[List[str]] = None, types: Optional[List[str]] = None) -> str:
        """Assemble the tool instruction text for prompt injection.

        `allowlist` (list of tool names) selects which tools to include: None = all;
        [] = none; [names] = only those. Cached by allowlist until the registry changes.
        """
        return await self._ensure_context_manager().get_instruction(allowlist=allowlist, types=types)

    async def function_callings(
        self, allowlist: Optional[List[str]] = None, types: Optional[List[str]] = None
    ) -> List[Tuple[Dict[str, Any], Tuple[Any, ...]]]:
        """Native tool-calling schemas for the selected tools, each paired with its
        dispatch route. Names are the tools' own registered names (already ``*_tool``,
        so no prefixing) — ``done_tool`` is an ordinary tool and comes through here too.

        ``allowlist``: None = all, [] = none, [names] = those. Returns
        ``[(function_calling, ("tool", name)), ...]``.
        """
        names = allowlist if allowlist is not None else await self.list()
        out: List[Tuple[Dict[str, Any], Tuple[Any, ...]]] = []
        for n in names:
            info = await self.get_info(n)
            if info is None:
                continue
            if types and getattr(info, "type", None) and info.type not in types:
                continue
            fc = await self.get_schema(n, format="json")
            if fc:
                out.append((fc, ("tool", n)))
        return out

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Return one Tool's canonical function schema as JSON or Markdown."""
        info = await self.get_info(name)
        if info is None:
            return None
        fc = getattr(info, "function_calling", None) or {}
        function = fc.get("function", {}) if isinstance(fc, dict) else {}
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            return None
        return CapabilitySchema(
            name=name, description=getattr(info, "description", "") or name,
            parameters=parameters,
            strict=parameters.get("additionalProperties") is False,
            source=SchemaSource.INFERRED,
        ).render(format)

    async def register(self,
                       tool: Union[Tool, Type[Tool]],
                       config: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None,
                       code: Optional[str] = None) -> ToolConfig:
        """Register a tool class or instance asynchronously.
        
        Args:
            tool: Tool class or instance to register
            config: Configuration dict for tool initialization (required when tool is a class)
            override: Whether to override existing registration
            version: Optional version string
            code: Optional explicit source code for the tool class
            
        Returns:
            ToolConfig: Tool configuration
        """
        tool_config = await self._ensure_context_manager().register(
            tool, 
            tool_config_dict=config, 
            override=override,
            version=version,
            code=code
        )
        self._registered_configs[tool_config.name] = tool_config
        return tool_config
    
    async def list(self) -> List[str]:
        """List all registered tools
        
        Args:
            include_disabled: Whether to include disabled tools
            
        Returns:
            List[str]: List of tool names
        """
        return await self._ensure_context_manager().list()
    
    
    async def get(self, tool_name: str) -> Tool:
        """Get tool configuration by name
        
        Args:
            tool_name: Tool name
            
        Returns:
            Tool: Tool instance or None if not found
        """
        tool = await self._ensure_context_manager().get(tool_name)
        # The parameter schema (function_calling) is generated onto the ToolConfig,
        # not the instance — attach it here so a tool passed to a model as
        # ``input["tools"]`` serializes correctly (serialize_tools reads
        # ``tool.function_calling``). Without this the tool is sent with name=None.
        if tool is not None and not getattr(tool, "function_calling", None):
            try:
                info = await self._ensure_context_manager().get_info(tool_name)
                if info is not None and getattr(info, "function_calling", None):
                    tool.function_calling = info.function_calling
            except Exception:
                pass
        return tool
    
    async def get_info(self, tool_name: str) -> Optional[ToolConfig]:
        """Get tool configuration by name
        
        Args:
            tool_name: Tool name
            
        Returns:
            ToolConfig: Tool configuration or None if not found
        """
        return await self._ensure_context_manager().get_info(tool_name)
    
    async def cleanup(self):
        """Cleanup all tools"""
        await self._ensure_context_manager().cleanup()
        self._registered_configs.clear()
    
    async def update(self,
                     tool_name: str, tool: Union[Tool, Type[Tool]],
                     config: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None,
                     description: Optional[str] = None,
                     code: Optional[str] = None) -> ToolConfig:
        """Update an existing tool with new configuration and create a new version

        Args:
            tool_name: Name of the tool to update
            tool: New tool class or instance with updated implementation
            config: Configuration dict for tool initialization (required when tool is a class)
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string (used when tool class is dynamically loaded)

        Returns:
            ToolConfig: Updated tool configuration
        """
        tool_cls = tool if isinstance(tool, type) else type(tool)
        tool_config = await self._ensure_context_manager().update(
            tool_cls, tool_config_dict=config, new_version=new_version, description=description, code=code
        )
        self._registered_configs[tool_config.name] = tool_config
        return tool_config
    
    async def copy(self, tool_name: str, new_name: Optional[str] = None,
                  new_version: Optional[str] = None, **override_config) -> ToolConfig:
        """Copy an existing tool
        
        Args:
            tool_name: Name of the tool to copy
            new_name: New name for the copied tool. If None, uses original name.
            new_version: New version for the copied tool. If None, increments version.
            **override_config: Configuration overrides
            
        Returns:
            ToolConfig: New tool configuration
        """
        tool_config = await self._ensure_context_manager().copy(
            tool_name, new_name, new_version, **override_config
        )
        self._registered_configs[tool_config.name] = tool_config
        return tool_config
    
    async def unregister(self, tool_name: str) -> bool:
        """Unregister a tool
        
        Args:
            tool_name: Name of the tool to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        success = await self._ensure_context_manager().unregister(tool_name)
        if success and tool_name in self._registered_configs:
            del self._registered_configs[tool_name]
        return success
    
    async def restore(self, tool_name: str, version: str, auto_initialize: bool = True) -> Optional[ToolConfig]:
        """Restore a specific version of a tool from history
        
        Args:
            tool_name: Name of the tool
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored tool
            
        Returns:
            ToolConfig of the restored version, or None if not found
        """
        tool_config = await self._ensure_context_manager().restore(tool_name, version, auto_initialize)
        if tool_config:
            self._registered_configs[tool_config.name] = tool_config
        return tool_config
    
    async def __call__(self, 
                       name: str, 
                       input: Dict[str, Any], 
                       ctx: ToolContext = None,
                       **kwargs
                       ) -> Response:
        """Call a tool by name with optional timeout and context
        
        Args:
            name: Tool name
            input: Input for the tool
            timeout: Timeout in seconds for this specific call (overrides default_timeout if provided)
            ctx: Tool context
            
        Returns:
            Response: Tool result
        """
        # Ensure ctx is always an ToolContext instance
        ctx = ToolContext.from_context(ctx) if ctx else ToolContext(name=name, input=input)
        return await self._ensure_context_manager()(name, input, ctx=ctx, **kwargs)


# Global tool manager instance
tool_manager = ToolManagerServer()
