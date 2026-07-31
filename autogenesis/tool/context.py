"""Tool Context Manager for managing tool lifecycle and resources with lazy loading."""
import os
import inspect
import asyncio
from asyncio_atexit import register as async_atexit_register
from typing import Any, Dict, List, Type, Optional, Union, Tuple, TYPE_CHECKING
from datetime import datetime
import inflection
import json
from pydantic import BaseModel, ConfigDict, Field


from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.utils import (assemble_workspace_path,
                       gather_with_concurrency,
                       file_lock,
                       render_capability_card,
                       )
from autogenesis.tool.types import Tool, ToolConfig, ToolContext
from autogenesis.response.types import Response, ResponseType
from autogenesis.version import version_manager
from autogenesis.dynamic import dynamic_manager
from autogenesis.registry import TOOL
from autogenesis.permission import permission_manager, PermissionMode

_UNSET = object()  # sentinel: get_instruction cache is empty / invalidated

class ToolContextManager(BaseModel):
    """Global context manager for all tools with lazy loading support."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="The base directory to use for the tools")
    
    def __init__(self, 
                 base_dir: Optional[str] = None,
                 model_name: str = "openrouter/gemini-3-flash-preview",
                 default_timeout: Optional[float] = 1800.0,
                 **kwargs):
        """Initialize the tool context manager.

        Args:
            base_dir: Base directory for storing tool data
            model_name: The model to use for the tools
            default_timeout: Default timeout in seconds for tool calls (None means no timeout, default 1800s = 30 minutes)
        """
        super().__init__(**kwargs)
        
        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "tool"))
        logger.info(f"| 📁 Tool context manager base directory: {self.base_dir}.")    
        logger.info(f"| 📁 Tool context manager.")

        self._tool_configs: Dict[str, ToolConfig] = {}  # Current active configs (latest version)
        # Tool version history, e.g., {"tool_name": {"1.0.0": ToolConfig, "1.0.1": ToolConfig}}
        self._tool_history_versions: Dict[str, Dict[str, ToolConfig]] = {}
        # get_instruction cache: (allowlist tuple) -> assembled text; invalidated on registry change.
        self._instr_key: Any = _UNSET
        self._instr_cache: str = ""

        self.model_name = model_name
        self.default_timeout = default_timeout

        self._cleanup_registered = False
        self._variables_lock = asyncio.Lock()  # Lock for get/set trainable variables
        
    async def initialize(self, tool_names: Optional[List[str]] = None):
        """Initialize the tool context manager."""
        
        # Register tool-related symbols for auto-injection in dynamic code
        dynamic_manager.register_symbol("TOOL", TOOL)
        dynamic_manager.register_symbol("Tool", Tool)
        dynamic_manager.register_symbol("Response", Response)
        dynamic_manager.register_symbol("ResponseType", ResponseType)

        # Register tool context provider for automatic import injection
        def tool_context_provider():
            """Provide tool-related imports for dynamic tool classes."""
            return {
                "TOOL": TOOL,
                "Tool": Tool,
                "Response": Response,
                "ResponseType": ResponseType,
            }
        dynamic_manager.register_context_provider("tool", tool_context_provider)
        
        # Load tools from TOOL registry
        tool_configs = {}
        registry_tool_configs: Dict[str, ToolConfig] = await self._load_from_registry()
        tool_configs.update(registry_tool_configs)
        
        # Load tools from code
        code_tool_configs: Dict[str, ToolConfig] = {}
        
        # Merge code configs with registry configs, only override if code version is strictly greater
        for tool_name, code_config in code_tool_configs.items():
            if tool_name in tool_configs:
                registry_config = tool_configs[tool_name]
                # Compare versions: only override if code version is strictly greater
                if version_manager.compare_versions(code_config.version, registry_config.version) > 0:
                    logger.info(f"| 🔄 Overriding tool {tool_name} from registry (v{registry_config.version}) with code version (v{code_config.version})")
                    tool_configs[tool_name] = code_config
                else:
                    logger.info(f"| 📌 Keeping tool {tool_name} from registry (v{registry_config.version}), code version (v{code_config.version}) is not greater")
                    # If versions are equal, update the history with registry config (which has real class, not dynamic)
                    if version_manager.compare_versions(code_config.version, registry_config.version) == 0:
                        # Replace the code config in history with registry config to preserve real class reference
                        if tool_name in self._tool_history_versions:
                            self._tool_history_versions[tool_name][registry_config.version] = registry_config
            else:
                # New tool from code, add it
                tool_configs[tool_name] = code_config
        
        # Filter tools by names if provided
        if tool_names is not None:
            tool_configs = {name: tool_configs[name] for name in tool_names}
        
        # Build all tools concurrently with a concurrency limit
        tool_names = list(tool_configs.keys())
        tasks = [
            self.build(tool_configs[name]) for name in tool_names
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)

        for tool_name, result in zip(tool_names, results):
            if isinstance(result, Exception):
                logger.error(f"| ❌ Failed to initialize tool {tool_name}: {result}")
                continue
            self._tool_configs[tool_name] = result
            logger.info(f"| 🔧 Tool {tool_name} initialized")
        
        # Save tool configs to json file
        # Save contract to file
        self._invalidate_instruction()
        
        # Register cleanup callback
        async_atexit_register(self.cleanup)
        self._cleanup_registered = True
        
        logger.info(f"| ✅ Tools initialization completed")
        
    async def _load_from_registry(self):
        """Load tools from TOOL registry."""
        
        tool_configs: Dict[str, ToolConfig] = {}
        
        async def register_tool_class(tool_cls: Type[Tool]):
            """Register a tool class synchronously.
            
            Args:
                tool_cls: Tool class to register
            """
            try:
                # Get tool config from global config
                tool_config_key = inflection.underscore(tool_cls.__name__)
                tool_config_dict = config.get(tool_config_key, {})
                tool_enable_evolving = tool_config_dict.get("enable_evolving", False) if tool_config_dict and "enable_evolving" in tool_config_dict else False
                
                # Get tool properties from tool class
                tool_name = tool_cls.model_fields['name'].default
                tool_description = tool_cls.model_fields['description'].default
                tool_metadata = tool_cls.model_fields['metadata'].default
                
                # Get or generate version from version_manager
                tool_version = await version_manager.get_version("tool", tool_name)
                
                # Get full module source code
                tool_code = dynamic_manager.get_full_module_source(tool_cls)
                
                tool_parameters = dynamic_manager.get_parameters(tool_cls)
                tool_function_calling = dynamic_manager.build_function_calling(tool_name, tool_description, tool_parameters)
                tool_text = dynamic_manager.build_text_representation(tool_name, tool_description, tool_parameters)
                tool_args_schema = dynamic_manager.build_args_schema(tool_name, tool_parameters)
                
                # Create tool config (ToolConfig.id is auto-incremented internally if needed)
                try:
                    tool_path = inspect.getfile(tool_cls)
                except Exception:
                    tool_path = None
                tool_config = ToolConfig(
                    name=tool_name,
                    description=tool_description,
                    version=tool_version,
                    cls=tool_cls,
                    config=tool_config_dict,
                    instance=None,
                    function_calling=tool_function_calling,
                    text=tool_text,
                    args_schema=tool_args_schema,
                    metadata=tool_metadata,
                    enable_evolving=tool_enable_evolving,
                    code=tool_code,
                    path=tool_path,
                )
                
                # Store tool config
                tool_configs[tool_name] = tool_config
                
                # Store in version history (by version string)
                if tool_name not in self._tool_history_versions:
                    self._tool_history_versions[tool_name] = {}
                self._tool_history_versions[tool_name][tool_version] = tool_config
                
                # Register version to version manager
                await version_manager.register_version("tool", tool_name, tool_version)
                
                logger.info(f"| 📝 Registered tool: {tool_name} ({tool_cls.__name__})")
                
            except Exception as e:
                logger.error(f"| ❌ Failed to register tool class {tool_cls.__name__}: {e}")
                raise
            
        import autogenesis.tool  # noqa: F401
        
        # Get all registered tool classes from TOOL registry
        tool_classes = list(TOOL._module_dict.values())
        
        logger.info(f"| 🔍 Discovering {len(tool_classes)} tools from TOOL registry")
        
        # Register each tool class concurrently with a concurrency limit
        tasks = [
            register_tool_class(tool_cls) for tool_cls in tool_classes
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        
        logger.info(f"| ✅ Discovered and registered {success_count}/{len(tool_classes)} tools from TOOL registry")
        
        return tool_configs
    
    async def build(self, tool_config: ToolConfig) -> ToolConfig:
        """Create a tool instance and store it.
        
        Args:
            tool_config: Tool configuration
            
        Returns:
            ToolConfig: Tool configuration with instance
        """
        if tool_config.name in self._tool_configs:
            existing_config = self._tool_configs[tool_config.name]
            if existing_config.instance is not None:
                return existing_config
        
        # Create new tool instance
        try:
            # cls should already be loaded (either from registry or from code)
            if tool_config.cls is None:
                raise ValueError(f"Cannot create tool {tool_config.name}: no class provided. Class should be loaded during initialization.")
            
            # Instantiate tool instance
            tool_instance = tool_config.cls(**tool_config.config) if tool_config.config else tool_config.cls()
            
            # Initialize tool if it has an initialize method
            if hasattr(tool_instance, "initialize"):
                await tool_instance.initialize()

            # Register with permission manager
            permission_manager.register(
                entity_name=tool_instance.name,
                mode=PermissionMode(tool_instance.permission_mode),
            )

            tool_config.instance = tool_instance

            # Store tool metadata
            self._tool_configs[tool_config.name] = tool_config

            logger.info(f"| 🔧 Tool {tool_config.name} created and stored")
            
            return tool_config
        except Exception as e:
            logger.error(f"| ❌ Failed to create tool {tool_config.name}: {e}")
            raise
    
    async def register(self, 
                       tool_cls: Type[Tool],
                       tool_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None,
                       code: Optional[str] = None) -> ToolConfig:
        """Register a tool class or instance.
        
        This will:
        - Create (or reuse) a tool instance
        - Create a `ToolConfig`
        - Store it as the current config and append to version history
        - Register the version in `version_manager` and FAISS index
        - Persist the tool source code (if available / provided)
        """
        
        try:
            if tool_config_dict is None:
                # Fallback to global config by class name
                tool_config_key = inflection.underscore(tool_cls.__name__)
                tool_config_dict = config.get(tool_config_key, {})
            
            # Instantiate tool immediately (register is a runtime operation)
            try:
                tool_instance = tool_cls(**tool_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create tool instance for {tool_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate tool {tool_cls.__name__} with provided config: {e}")
            
            tool_name = tool_instance.name
            tool_description = tool_instance.description
            tool_metadata = tool_instance.metadata
            # Get enable_evolving from tool_config_dict if provided, otherwise from tool_instance
            tool_enable_evolving = tool_config_dict.get("enable_evolving", tool_instance.enable_evolving) if tool_config_dict and "enable_evolving" in tool_config_dict else tool_instance.enable_evolving

            # Register with permission manager
            permission_manager.register(
                entity_name=tool_name,
                mode=PermissionMode(tool_instance.permission_mode),
            )

            # Get or generate version from version_manager
            if version is None:
                tool_version = await version_manager.get_version("tool", tool_name)
            else:
                tool_version = version
                
            # Get tool code (prefer explicit code if provided)
            tool_code = code if code is not None else dynamic_manager.get_source_code(tool_cls)
            if not tool_code:
                logger.warning(f"| ⚠️ Tool {tool_name} is dynamic but source code cannot be extracted (and no code was provided)")
            
            # Get tool parameters
            tool_parameters = dynamic_manager.get_parameters(tool_cls)
            tool_function_calling = dynamic_manager.build_function_calling(tool_name, tool_description, tool_parameters)
            tool_text = dynamic_manager.build_text_representation(tool_name, tool_description, tool_parameters)
            tool_args_schema = dynamic_manager.build_args_schema(tool_name, tool_parameters)
            
            # --- Build ToolConfig ---
            # Dynamically-loaded extension classes have no real module file, so
            # inspect.getfile() fails on them. The extension loader stamps the
            # active source path onto the class as __source_file__ — prefer it.
            tool_path = getattr(tool_cls, "__source_file__", None)
            if not tool_path:
                try:
                    tool_path = inspect.getfile(tool_cls)
                except Exception:
                    tool_path = None
            tool_config = ToolConfig(
                name=tool_name,
                description=tool_description,
                metadata=tool_metadata,
                enable_evolving=tool_enable_evolving,
                version=tool_version,
                cls=tool_cls,
                config=tool_config_dict or {},
                instance=tool_instance,
                function_calling=tool_function_calling,
                text=tool_text,
                args_schema=tool_args_schema,
                code=tool_code,
                path=tool_path,
            )
            
            # --- Persist current config and history ---
            self._tool_configs[tool_name] = tool_config
            
            # Store in dict-based history (for quick lookup by version)
            if tool_name not in self._tool_history_versions:
                self._tool_history_versions[tool_name] = {}
            self._tool_history_versions[tool_name][tool_config.version] = tool_config
            
            # Register version in version manager
            await version_manager.register_version("tool", tool_name, tool_config.version)
            
            # Persist to JSON
            # Save contract to file
            self._invalidate_instruction()
            
            logger.info(f"| 📝 Registered tool config: {tool_name}: {tool_config.version}")
            return tool_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to register tool: {e}")
            raise
    
    
    async def get(self, tool_name: str) -> Tool:
        """Get tool configuration by name
        
        Args:
            tool_name: Tool name
            
        Returns:
            Tool: Tool instance or None if not found
        """
        tool_config = self._tool_configs.get(tool_name)
        if tool_config is None:
            return None
        return tool_config.instance if tool_config.instance is not None else None
    
    async def get_info(self, tool_name: str) -> Optional[ToolConfig]:
        """Get tool info by name
        
        Args:
            tool_name: Tool name
            
        Returns:
            ToolConfig: Tool info or None if not found
        """
        return self._tool_configs.get(tool_name)
    
    async def list(self) -> List[str]:
        """Get list of registered tools
        
        Returns:
            List[str]: List of tool names
        """
        return [name for name in self._tool_configs.keys()]
    
    async def update(self, 
                     tool_cls: Type[Tool],
                     tool_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None,
                     code: Optional[str] = None) -> ToolConfig:
        """Update an existing tool with new configuration and create a new version
        
        Args:
            tool_cls: New tool class with updated implementation
            tool_config_dict: Configuration dict for tool initialization
                   If None, will try to get from global config
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string. If provided, uses this instead of extracting from tool_cls.
                  This is useful when tool_cls is dynamically created from code string.
            
        Returns:
            ToolConfig: Updated tool configuration
        """
        try:
            if tool_config_dict is None:
                # Fallback to global config by class name
                tool_config_key = inflection.underscore(tool_cls.__name__)
                tool_config_dict = config.get(tool_config_key, {})
            
            # Instantiate tool immediately (update is a runtime operation)
            try:
                tool_instance = tool_cls(**tool_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create tool instance for {tool_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate tool {tool_cls.__name__} with provided config: {e}")
            
            tool_name = tool_instance.name
            
            # Check if tool exists
            original_config = self._tool_configs.get(tool_name)
            if original_config is None:
                raise ValueError(f"Tool {tool_name} not found. Use register() to register a new tool.")
            
            tool_description = tool_instance.description
            tool_metadata = tool_instance.metadata
            # Get enable_evolving from tool_config_dict if provided, otherwise from tool_instance
            tool_enable_evolving = tool_config_dict.get("enable_evolving", tool_instance.enable_evolving) if tool_config_dict and "enable_evolving" in tool_config_dict else tool_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                # Get current version from version_manager and generate next patch version
                new_version = await version_manager.generate_next_version("tool", tool_name, "patch")
            
            # Get tool code - use provided code if available (for dynamically created classes)
            if code is not None:
                tool_code = code
            else:
                tool_code = dynamic_manager.get_source_code(tool_cls)
                if not tool_code:
                    logger.warning(f"| ⚠️ Tool {tool_name} is dynamic but source code cannot be extracted")
            
            # Get tool parameters and build properties using dynamic_manager methods
            tool_parameters = dynamic_manager.get_parameters(tool_cls)
            tool_function_calling = dynamic_manager.build_function_calling(tool_name, tool_description, tool_parameters)
            tool_text = dynamic_manager.build_text_representation(tool_name, tool_description, tool_parameters)
            tool_args_schema = dynamic_manager.build_args_schema(tool_name, tool_parameters)
            
            # --- Build ToolConfig ---
            updated_config = ToolConfig(
                name=tool_name,  # Keep same name
                description=tool_description,
                metadata=tool_metadata,
                enable_evolving=tool_enable_evolving,
                version=new_version,
                cls=tool_cls,
                config=tool_config_dict or {},
                instance=tool_instance,
                function_calling=tool_function_calling,
                text=tool_text,
                args_schema=tool_args_schema,
                code=tool_code,
            )
            
            # Update the tool config (replaces current version)
            self._tool_configs[tool_name] = updated_config
            
            # Store in version history
            if tool_name not in self._tool_history_versions:
                self._tool_history_versions[tool_name] = {}
            self._tool_history_versions[tool_name][updated_config.version] = updated_config
            
            # Register new version record to version manager
            await version_manager.register_version(
                "tool", 
                tool_name, 
                new_version,
                description=description or f"Updated from {original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            self._invalidate_instruction()
            
            logger.info(f"| 🔄 Updated tool {tool_name} from v{original_config.version} to v{new_version}")
            return updated_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to update tool: {e}")
            raise
    
    async def copy(self, 
                  tool_name: str,
                  new_name: Optional[str] = None, 
                  new_version: Optional[str] = None, 
                  new_config: Optional[Dict[str, Any]] = None) -> ToolConfig:
        """Copy an existing tool configuration
        
        Args:
            tool_name: Name of the tool to copy
            new_name: New name for the copied tool. If None, uses original name.
            new_version: New version for the copied tool. If None, increments version.
            new_config: New configuration dict for the copied tool. If None, uses original config.
            
        Returns:
            ToolConfig: New tool configuration
        """
        try:
            original_config = self._tool_configs.get(tool_name)
            if original_config is None:
                raise ValueError(f"Tool {tool_name} not found")
            
            if original_config.cls is None:
                raise ValueError(f"Cannot copy tool {tool_name}: no class provided")
            
            # Determine new name
            if new_name is None:
                new_name = tool_name
            
            # Prepare config dict (merge original config with new config)
            tool_config_dict = original_config.config.copy() if original_config.config else {}
            if new_config:
                # Merge new config into original config
                tool_config_dict.update(new_config)
            
            # Instantiate tool instance (copy is a runtime operation)
            try:
                tool_instance = original_config.cls(**tool_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create tool instance for {original_config.cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate tool {original_config.cls.__name__} with provided config: {e}")
            
            # Apply name override if provided (after instantiation)
            if new_name != tool_name:
                tool_instance.name = new_name
            
            tool_description = tool_instance.description
            tool_metadata = tool_instance.metadata
            tool_enable_evolving = tool_config_dict.get("enable_evolving", tool_instance.enable_evolving) if tool_config_dict and "enable_evolving" in tool_config_dict else tool_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                if new_name == tool_name:
                    # If copying with same name, get next version from version_manager
                    new_version = await version_manager.generate_next_version("tool", new_name, "patch")
                else:
                    # If copying with different name, get or generate version for new name
                    new_version = await version_manager.get_version("tool", new_name)
            
            # Get tool code
            tool_code = dynamic_manager.get_source_code(original_config.cls)
            if not tool_code:
                logger.warning(f"| ⚠️ Tool {new_name} is dynamic but source code cannot be extracted")
            
            # Get tool parameters and build properties using dynamic_manager methods
            tool_parameters = dynamic_manager.get_parameters(original_config.cls)
            tool_function_calling = dynamic_manager.build_function_calling(new_name, tool_description, tool_parameters)
            tool_text = dynamic_manager.build_text_representation(new_name, tool_description, tool_parameters)
            tool_args_schema = dynamic_manager.build_args_schema(new_name, tool_parameters)
            
            # --- Build ToolConfig ---
            new_config = ToolConfig(
                name=new_name,
                description=tool_description,
                metadata=tool_metadata,
                enable_evolving=tool_enable_evolving,
                version=new_version,
                cls=original_config.cls,
                config=tool_config_dict,
                instance=tool_instance,
                function_calling=tool_function_calling,
                text=tool_text,
                args_schema=tool_args_schema,
                code=tool_code,
            )
            
            # Register new tool
            self._tool_configs[new_name] = new_config
            
            # Store in version history
            if new_name not in self._tool_history_versions:
                self._tool_history_versions[new_name] = {}
            self._tool_history_versions[new_name][new_version] = new_config
            
            # Register version record to version manager
            await version_manager.register_version(
                "tool", 
                new_name, 
                new_version,
                description=f"Copied from {tool_name}@{original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            self._invalidate_instruction()
            
            logger.info(f"| 📋 Copied tool {tool_name}@{original_config.version} to {new_name}@{new_version}")
            return new_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to copy tool: {e}")
            raise
    
    async def unregister(self, tool_name: str) -> bool:
        """Unregister a tool
        
        Args:
            tool_name: Name of the tool to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        if tool_name not in self._tool_configs:
            logger.warning(f"| ⚠️ Tool {tool_name} not found")
            return False
        
        tool_config = self._tool_configs[tool_name]
        
        # Remove from configs
        del self._tool_configs[tool_name]

        # Persist to JSON after unregister
        # Save contract to file
        self._invalidate_instruction()
        
        logger.info(f"| 🗑️ Unregistered tool {tool_name}@{tool_config.version}")
        return True
    
    async def restore(self, tool_name: str, version: str, auto_initialize: bool = True) -> Optional[ToolConfig]:
        """Restore a specific version of a tool from history
        
        Args:
            tool_name: Name of the tool
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored tool
            
        Returns:
            ToolConfig of the restored version, or None if not found
        """
        # Look up version from dict-based history (O(1) lookup)
        version_config = None
        if tool_name in self._tool_history_versions:
            version_config = self._tool_history_versions[tool_name].get(version)
        
        if version_config is None:
            logger.warning(f"| ⚠️ Version {version} not found for tool {tool_name}")
            return None
        
        # Create a copy to avoid modifying the history
        restored_config = ToolConfig(**version_config.model_dump())
        
        # Set as current active config
        self._tool_configs[tool_name] = restored_config
        
        # Update version manager current version
        version_history = await version_manager.get_version_history("tool", tool_name)
        if version_history:
            # Check if version exists in version history, if not register it
            if version not in version_history.versions:
                await version_manager.register_version("tool", tool_name, version)
            version_history.current_version = version
        else:
            # If version history doesn't exist, register the version first
            await version_manager.register_version("tool", tool_name, version)
        
        # Initialize if requested
        if auto_initialize and restored_config.cls is not None:
            await self.build(restored_config)
        
        # Persist to JSON (current_version changes)
        
        logger.info(f"| 🔄 Restored tool {tool_name} to version {version}")
        return restored_config
    
    async def get_instruction(self, allowlist=None, types=None) -> str:
        """Assemble the tool instruction text for prompt injection, on demand.

        Each tool renders its name + description + full `_INSTRUCTION` (Function /
        Guidance / Parameters / Example) so the agent has the arguments inline and
        rarely needs `inspect_tool`. These are the agent's resident tools (its
        configured set), so the set is small and inlining the instruction is affordable.

        `allowlist` (list of tool names) selects which tools to include: None = all
        loaded tools; [] = none; [names] = only those. Cached by allowlist and reused
        until the registry changes (register/update/remove call `_invalidate_instruction`).
        `types` is accepted for a uniform manager interface but tools have no type filter.
        """
        key = None if allowlist is None else tuple(allowlist)
        if key == self._instr_key:
            return self._instr_cache
        targets = list(self._tool_configs.keys()) if allowlist is None else allowlist
        parts = []
        for name in targets:
            info = await self.get_info(name)
            if info is None:
                continue
            block = render_capability_card(
                name=info.name,
                description=(info.description or ""),
                body=(getattr(info, "instruction", "") or ""),
            )
            parts.append(block)
        text = "\n\n".join(parts)
        self._instr_key = key
        self._instr_cache = text
        return text

    def _invalidate_instruction(self) -> None:
        """Drop the cached instruction so the next get_instruction rebuilds it."""
        self._instr_key = _UNSET
    
    async def cleanup(self):
        """Cleanup all active tools."""
        try:
            # Clear all tool configs and version history
            self._tool_configs.clear()
            self._tool_history_versions.clear()
                
            logger.info("| 🧹 Tool context manager cleaned up")
            
        except Exception as e:
            logger.error(f"| ❌ Error during tool context manager cleanup: {e}")
            
    async def __call__(self,
                       name: str,
                       input: Dict[str, Any],
                       ctx: ToolContext = None,
                       **kwargs
                       ) -> Response:
        """Call a tool by name with optional timeout

        Args:
            name: Tool name
            input: Input for the tool
            ctx: Optional tool context to pass to the tool
        Returns:
            Response: Tool result
        """
        tool_info = await self.get_info(name)
        
        if tool_info is None:
            error_msg = f"Tool '{name}' is not registered. Available tools: {list(self._tool_configs.keys())}"
            logger.error(f"| ❌ {error_msg}")
            return Response(type=ResponseType.TOOL, success=False, message=error_msg)
        
        version = tool_info.version
        tool_instance = tool_info.instance
        logger.info(f"| ✅ Using tool {name}@{version}")

        # Other tool args
        tool_kwargs = dict(ctx=ctx, **kwargs)

        # A model's tool call may omit a required parameter or pass an unknown one
        # (e.g. done_tool without `result`). Binding that to the tool's signature would
        # raise a raw TypeError that bubbles up as an opaque "Action failed:
        # __call__() missing 1 required positional argument" — internal noise the model
        # cannot act on cleanly. Validate the binding first and, on failure, hand back a
        # structured, recoverable error that names the offending call and the parameters
        # the tool actually expects, so the agent can simply re-issue the call. The real
        # invocation below is unchanged, so any TypeError raised *inside* the tool body
        # still surfaces normally.
        try:
            inspect.signature(tool_instance.__call__).bind(**input, **tool_kwargs)
        except TypeError as bind_error:
            required = [
                p.name
                for p in inspect.signature(tool_instance.__call__).parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
                and p.name not in ("self", "ctx")
            ]
            msg = (
                f"Invalid arguments for tool '{name}': {bind_error}. "
                f"Required parameter(s): {required}. Re-issue the call with all required parameters."
            )
            logger.warning(f"| ⚠️ {msg}")
            return Response(type=ResponseType.TOOL, success=False, message=msg)

        # Otherwise, use asyncio.wait_for to enforce timeout
        try:
            return await asyncio.wait_for(tool_instance(**input, **tool_kwargs), timeout=self.default_timeout)
        except asyncio.TimeoutError:
            error_msg = f"Tool '{name}' execution timed out after {self.default_timeout} seconds"
            logger.error(f"| ⏱️ {error_msg}")
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message=error_msg,
            )
