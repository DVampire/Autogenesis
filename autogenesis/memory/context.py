"""Memory Context Manager for managing memory lifecycle and resources with lazy loading."""
import asyncio
import os
from asyncio_atexit import register as async_atexit_register
from typing import Any, Dict, List, Type, Optional, Union, Tuple
from datetime import datetime
import inflection
import json
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.version import version_manager
from autogenesis.utils import (assemble_workspace_path,
                       gather_with_concurrency,
                       file_lock
                       )
from autogenesis.memory.types import MemoryConfig, Memory
from autogenesis.session import SessionContext
from autogenesis.memory.types import MemoryContext
from autogenesis.dynamic import dynamic_manager
from autogenesis.registry import MEMORY_SYSTEM
from autogenesis.permission import permission_manager, PermissionMode

class MemoryContextManager(BaseModel):
    """Global context manager for all memory systems with lazy loading support."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="The base directory to use for the memory systems")
    
    def __init__(self, 
                 base_dir: Optional[str] = None,
                 **kwargs):
        """Initialize the memory context manager.
        
        Args:
            base_dir: Base directory for storing memory data
        """
        super().__init__(**kwargs)
        
        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "memory"))
        logger.info(f"| 📁 Memory context manager base directory: {self.base_dir}.")    
        logger.info(f"| 📁 Memory context manager.")

        self._memory_configs: Dict[str, MemoryConfig] = {}  # Current active configs (latest version)
        # Memory version history, e.g., {"memory_name": {"1.0.0": MemoryConfig, "1.0.1": MemoryConfig}}
        self._memory_history_versions: Dict[str, Dict[str, MemoryConfig]] = {}
        
        self._cleanup_registered = False
        self._variables_lock = asyncio.Lock()  # Lock for get/set trainable variables
    
    async def initialize(self, memory_names: Optional[List[str]] = None):
        """Initialize the memory context manager."""
        # Register memory-related symbols for auto-injection in dynamic code
        dynamic_manager.register_symbol("MEMORY_SYSTEM", MEMORY_SYSTEM)
        dynamic_manager.register_symbol("Memory", Memory)
        
        # Register memory context provider for automatic import injection
        def memory_context_provider():
            """Provide memory-related imports for dynamic memory classes."""
            return {
                "MEMORY_SYSTEM": MEMORY_SYSTEM,
                "Memory": Memory,
            }
        dynamic_manager.register_context_provider("memory", memory_context_provider)
        
        # Load memory systems from MEMORY_SYSTEM registry
        memory_configs = {}
        registry_memory_configs: Dict[str, MemoryConfig] = await self._load_from_registry()
        memory_configs.update(registry_memory_configs)
        
        # Load memory systems from code (JSON file)
        code_memory_configs: Dict[str, MemoryConfig] = {}
        
        # Merge code configs with registry configs, only override if code version is strictly greater
        for memory_name, code_config in code_memory_configs.items():
            if memory_name in memory_configs:
                registry_config = memory_configs[memory_name]
                # Compare versions: only override if code version is strictly greater
                if version_manager.compare_versions(code_config.version, registry_config.version) > 0:
                    logger.info(f"| 🔄 Overriding memory {memory_name} from registry (v{registry_config.version}) with code version (v{code_config.version})")
                    memory_configs[memory_name] = code_config
                else:
                    logger.info(f"| 📌 Keeping memory {memory_name} from registry (v{registry_config.version}), code version (v{code_config.version}) is not greater")
                    # If versions are equal, update the history with registry config (which has real class, not dynamic)
                    if version_manager.compare_versions(code_config.version, registry_config.version) == 0:
                        # Replace the code config in history with registry config to preserve real class reference
                        if memory_name in self._memory_history_versions:
                            self._memory_history_versions[memory_name][registry_config.version] = registry_config
            else:
                # New memory from code, add it
                memory_configs[memory_name] = code_config
        
        # Filter memory systems by names if provided
        if memory_names is not None:
            memory_configs = {name: memory_configs[name] for name in memory_names if name in memory_configs}
        
        # Build all memory systems concurrently with a concurrency limit
        memory_names_list = list(memory_configs.keys())
        tasks = [
            self.build(memory_configs[name]) for name in memory_names_list
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)

        for memory_name, result in zip(memory_names_list, results):
            if isinstance(result, Exception):
                logger.error(f"| ❌ Failed to initialize memory {memory_name}: {result}")
                continue
            self._memory_configs[memory_name] = result
            logger.info(f"| 🔧 Memory {memory_name} initialized")
        
        # Save memory configs to json file
        # Save contract to file
        
        # Register cleanup callback
        async_atexit_register(self.cleanup)
        self._cleanup_registered = True
        
        logger.info(f"| ✅ Memory systems initialization completed")
    
    async def _load_from_registry(self):
        """Load memory systems from MEMORY_SYSTEM registry."""
        
        memory_configs: Dict[str, MemoryConfig] = {}
        
        async def register_memory_class(memory_cls: Type[Memory]):
            """Register a memory class synchronously.
            
            Args:
                memory_cls: Memory class to register
            """
            try:
                # Get memory config from global config
                memory_config_key = inflection.underscore(memory_cls.__name__)
                memory_config_dict = config.get(memory_config_key, {})
                memory_enable_evolving = memory_config_dict.get("enable_evolving", False) if memory_config_dict and "enable_evolving" in memory_config_dict else False
                
                # Create temporary instance to get name and description
                try:
                    temp_instance = memory_cls(**memory_config_dict)
                    memory_name = temp_instance.name
                    memory_description = temp_instance.description
                except Exception:
                    # If instantiation fails, try without config
                    try:
                        temp_instance = memory_cls()
                        memory_name = temp_instance.name
                        memory_description = temp_instance.description
                    except Exception:
                        # If still fails, try to get from class attributes or use defaults
                        memory_name = getattr(memory_cls, 'name', None)
                        memory_description = getattr(memory_cls, 'description', '')
                        if not memory_name:
                            # Use class name as fallback
                            memory_name = inflection.underscore(memory_cls.__name__)
                        if not memory_description:
                            memory_description = memory_cls.__doc__ or ""
                
                # Get or generate version from version_manager
                memory_version = await version_manager.get_version("memory", memory_name)
                
                # Get full module source code
                memory_code = dynamic_manager.get_full_module_source(memory_cls)
                
                # Create memory config
                memory_config = MemoryConfig(
                    name=memory_name,
                    description=memory_description,
                    enable_evolving=memory_enable_evolving,
                    version=memory_version,
                    cls=memory_cls,
                    config=memory_config_dict,
                    instance=None,
                    metadata={},
                    code=memory_code,
                )
                
                # Store memory config
                memory_configs[memory_name] = memory_config
                
                # Store in version history (by version string)
                if memory_name not in self._memory_history_versions:
                    self._memory_history_versions[memory_name] = {}
                self._memory_history_versions[memory_name][memory_version] = memory_config
                
                # Register version to version manager
                await version_manager.register_version("memory", memory_name, memory_version)
                
                logger.info(f"| 📝 Registered memory: {memory_name} ({memory_cls.__name__})")
                
            except Exception as e:
                logger.error(f"| ❌ Failed to register memory class {memory_cls.__name__}: {e}")
                raise
            
        import autogenesis.memory  # noqa: F401
        
        # Get all registered memory classes from MEMORY_SYSTEM registry
        memory_classes = list(MEMORY_SYSTEM._module_dict.values())
        
        logger.info(f"| 🔍 Discovering {len(memory_classes)} memory systems from MEMORY_SYSTEM registry")
        
        # Register each memory class concurrently with a concurrency limit
        tasks = [
            register_memory_class(memory_cls) for memory_cls in memory_classes
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        
        logger.info(f"| ✅ Discovered and registered {success_count}/{len(memory_classes)} memory systems from MEMORY_SYSTEM registry")
        
        return memory_configs
    
    async def register(self, 
                       memory: Union[Memory, Type[Memory]],
                       memory_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None) -> MemoryConfig:
        """Register a memory class or instance.
        
        This will:
        - Create (or reuse) a memory instance
        - Create a `MemoryConfig`
        - Store it as the current config and append to version history
        - Register the version in `version_manager`
        
        Args:
            memory: Memory instance or class
            memory_config_dict: Configuration dict for memory initialization (required when memory is a class)
            override: Whether to override existing registration
            version: Optional version string
            
        Returns:
            MemoryConfig: Memory configuration
        """
        
        try:
            # Handle both instance and class cases
            if isinstance(memory, Memory):
                # Registering an instance
                memory_instance = memory
                memory_cls = type(memory)
                if memory_config_dict:
                    raise ValueError("Extra keyword arguments are not allowed when registering memory instances.")
                memory_config_dict = {}
            else:
                # Registering a class
                memory_cls = memory
                if memory_config_dict is None:
                    # Fallback to global config by class name
                    memory_config_key = inflection.underscore(memory_cls.__name__)
                    memory_config_dict = config.get(memory_config_key, {})
                
                # Instantiate memory immediately (register is a runtime operation)
                try:
                    memory_instance = memory_cls(**memory_config_dict)
                except Exception as e:
                    logger.error(f"| ❌ Failed to create memory instance for {memory_cls.__name__}: {e}")
                    raise ValueError(f"Failed to instantiate memory {memory_cls.__name__} with provided config: {e}")
            
            memory_name = memory_instance.name
            memory_description = memory_instance.description
            memory_metadata = getattr(memory_instance, 'metadata', {})
            # Get enable_evolving from memory_config_dict if provided, otherwise from memory_instance
            memory_enable_evolving = memory_config_dict.get("enable_evolving", memory_instance.enable_evolving) if memory_config_dict and "enable_evolving" in memory_config_dict else memory_instance.enable_evolving

            # Register with permission manager
            permission_manager.register(
                entity_name=memory_name,
                mode=PermissionMode(getattr(memory_instance, "permission_mode", "workspace_write")),
            )

            if not memory_name:
                raise ValueError("Memory.name cannot be empty.")
            
            if memory_name in self._memory_configs and not override:
                raise ValueError(f"Memory '{memory_name}' already registered. Use override=True to replace it.")
            
            # Get or generate version from version_manager
            if version is None:
                memory_version = await version_manager.get_version("memory", memory_name)
            else:
                memory_version = version
                
            # Get memory code
            memory_code = dynamic_manager.get_full_module_source(memory_cls)
            if not memory_code:
                logger.warning(f"| ⚠️ Memory {memory_name} source code cannot be extracted")
            
            # --- Build MemoryConfig ---
            memory_config = MemoryConfig(
                name=memory_name,
                description=memory_description,
                enable_evolving=memory_enable_evolving,
                version=memory_version,
                cls=memory_cls,
                config=memory_config_dict or {},
                instance=memory_instance if isinstance(memory, Memory) else None,
                metadata=memory_metadata,
                code=memory_code,
            )
            
            # --- Persist current config and history ---
            self._memory_configs[memory_name] = memory_config
            
            # Store in dict-based history (for quick lookup by version)
            if memory_name not in self._memory_history_versions:
                self._memory_history_versions[memory_name] = {}
            self._memory_history_versions[memory_name][memory_config.version] = memory_config
            
            # Register version in version manager
            await version_manager.register_version("memory", memory_name, memory_config.version)
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 📝 Registered memory config: {memory_name}: {memory_config.version}")
            return memory_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to register memory: {e}")
            raise
    
    async def update(self, 
                     memory_name: str,
                     memory: Union[Memory, Type[Memory]],
                     memory_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None,
                     code: Optional[str] = None) -> MemoryConfig:
        """Update an existing memory system with new configuration and create a new version
        
        Args:
            memory_name: Name of the memory system to update
            memory: New memory instance or class with updated implementation
            memory_config_dict: Configuration dict for memory initialization
                   If None, will try to get from global config
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string. If provided, uses this instead of extracting from memory class.
                  This is useful when memory class is dynamically created from code string.
            
        Returns:
            MemoryConfig: Updated memory configuration
        """
        try:
            # Handle both instance and class cases
            if isinstance(memory, Memory):
                # Updating with an instance
                memory_instance = memory
                memory_cls = type(memory)
                if memory_config_dict:
                    raise ValueError("Extra keyword arguments are not allowed when updating with memory instances.")
                memory_config_dict = {}
            else:
                # Updating with a class
                memory_cls = memory
                if memory_config_dict is None:
                    # Fallback to global config by class name
                    memory_config_key = inflection.underscore(memory_cls.__name__)
                    memory_config_dict = config.get(memory_config_key, {})
                
                # Instantiate memory immediately (update is a runtime operation)
                try:
                    memory_instance = memory_cls(**memory_config_dict)
                except Exception as e:
                    logger.error(f"| ❌ Failed to create memory instance for {memory_cls.__name__}: {e}")
                    raise ValueError(f"Failed to instantiate memory {memory_cls.__name__} with provided config: {e}")
            
            # Check if memory exists
            original_config = self._memory_configs.get(memory_name)
            if original_config is None:
                raise ValueError(f"Memory {memory_name} not found. Use register() to register a new memory system.")
            
            memory_description = memory_instance.description
            memory_metadata = getattr(memory_instance, 'metadata', {})
            # Get enable_evolving from memory_config_dict if provided, otherwise from memory_instance
            memory_enable_evolving = memory_config_dict.get("enable_evolving", memory_instance.enable_evolving) if memory_config_dict and "enable_evolving" in memory_config_dict else memory_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                # Get current version from version_manager and generate next patch version
                new_version = await version_manager.generate_next_version("memory", memory_name, "patch")
            
            # Get memory code - use provided code if available (for dynamically created classes)
            if code is not None:
                memory_code = code
            else:
                memory_code = dynamic_manager.get_full_module_source(memory_cls)
                if not memory_code:
                    logger.warning(f"| ⚠️ Memory {memory_name} source code cannot be extracted")
            
            # --- Build MemoryConfig ---
            updated_config = MemoryConfig(
                name=memory_name,  # Keep same name
                description=memory_description,
                enable_evolving=memory_enable_evolving,
                version=new_version,
                cls=memory_cls,
                config=memory_config_dict or {},
                instance=memory_instance,  # Always use the created instance
                metadata=memory_metadata,
                code=memory_code,
            )
            
            # Update the memory config (replaces current version)
            self._memory_configs[memory_name] = updated_config
            
            # Store in version history
            if memory_name not in self._memory_history_versions:
                self._memory_history_versions[memory_name] = {}
            self._memory_history_versions[memory_name][updated_config.version] = updated_config
            
            # Register new version record to version manager
            await version_manager.register_version(
                "memory", 
                memory_name, 
                new_version,
                description=description or f"Updated from {original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 🔄 Updated memory {memory_name} from v{original_config.version} to v{new_version}")
            return updated_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to update memory: {e}")
            raise
    
    async def copy(self, 
                  memory_name: str,
                  new_name: Optional[str] = None, 
                  new_version: Optional[str] = None, 
                  new_config: Optional[Dict[str, Any]] = None) -> MemoryConfig:
        """Copy an existing memory configuration
        
        Args:
            memory_name: Name of the memory system to copy
            new_name: New name for the copied memory. If None, uses original name.
            new_version: New version for the copied memory. If None, increments version.
            new_config: New configuration dict for the copied memory. If None, uses original config.
            
        Returns:
            MemoryConfig: New memory configuration
        """
        try:
            original_config = self._memory_configs.get(memory_name)
            if original_config is None:
                raise ValueError(f"Memory {memory_name} not found")
            
            if original_config.cls is None:
                raise ValueError(f"Cannot copy memory {memory_name}: no class provided")
            
            # Determine new name
            if new_name is None:
                new_name = memory_name
            
            # Prepare config dict (merge original config with new config)
            memory_config_dict = original_config.config.copy() if original_config.config else {}
            if new_config:
                # Merge new config into original config
                memory_config_dict.update(new_config)
            
            # Instantiate memory instance (copy is a runtime operation)
            try:
                memory_instance = original_config.cls(**memory_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create memory instance for {original_config.cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate memory {original_config.cls.__name__} with provided config: {e}")
            
            # Apply name override if provided (after instantiation)
            if new_name != memory_name:
                memory_instance.name = new_name
            
            memory_description = memory_instance.description
            memory_metadata = getattr(memory_instance, 'metadata', {})
            memory_enable_evolving = memory_config_dict.get("enable_evolving", memory_instance.enable_evolving) if memory_config_dict and "enable_evolving" in memory_config_dict else memory_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                if new_name == memory_name:
                    # If copying with same name, get next version from version_manager
                    new_version = await version_manager.generate_next_version("memory", new_name, "patch")
                else:
                    # If copying with different name, get or generate version for new name
                    new_version = await version_manager.get_version("memory", new_name)
            
            # Get memory code
            memory_code = dynamic_manager.get_full_module_source(original_config.cls)
            if not memory_code:
                logger.warning(f"| ⚠️ Memory {new_name} source code cannot be extracted")
            
            # --- Build MemoryConfig ---
            new_memory_config = MemoryConfig(
                name=new_name,
                description=memory_description,
                enable_evolving=memory_enable_evolving,
                version=new_version,
                cls=original_config.cls,
                config=memory_config_dict,
                instance=memory_instance,
                metadata=memory_metadata,
                code=memory_code,
            )
            
            # Register new memory
            self._memory_configs[new_name] = new_memory_config
            
            # Store in version history
            if new_name not in self._memory_history_versions:
                self._memory_history_versions[new_name] = {}
            self._memory_history_versions[new_name][new_version] = new_memory_config
            
            # Register version record to version manager
            await version_manager.register_version(
                "memory", 
                new_name, 
                new_version,
                description=f"Copied from {memory_name}@{original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 📋 Copied memory {memory_name}@{original_config.version} to {new_name}@{new_version}")
            return new_memory_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to copy memory: {e}")
            raise
    
    async def unregister(self, memory_name: str) -> bool:
        """Unregister a memory system
        
        Args:
            memory_name: Name of the memory system to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        if memory_name not in self._memory_configs:
            logger.warning(f"| ⚠️ Memory {memory_name} not found")
            return False
        
        memory_config = self._memory_configs[memory_name]
        
        # Remove from configs
        del self._memory_configs[memory_name]

        # Persist to JSON after unregister
        # Save contract to file
        
        logger.info(f"| 🗑️ Unregistered memory {memory_name}@{memory_config.version}")
        return True
    
    async def get(self, memory_name: str) -> Memory:
        """Get memory configuration by name
        
        Args:
            memory_name: Memory name
            
        Returns:
            Memory: Memory instance or None if not found
        """
        memory_config = self._memory_configs.get(memory_name)
        if memory_config is None:
            return None
        return memory_config.instance if memory_config.instance is not None else None
    
    async def get_info(self, memory_name: str) -> Optional[MemoryConfig]:
        """Get memory info by name
        
        Args:
            memory_name: Memory name
            
        Returns:
            MemoryConfig: Memory info or None if not found
        """
        return self._memory_configs.get(memory_name)
    
    async def list(self) -> List[str]:
        """Get list of registered memory systems
        
        Returns:
            List[str]: List of memory system names
        """
        return [name for name in self._memory_configs.keys()]
    
    async def build(self, memory_config: MemoryConfig) -> MemoryConfig:
        """Create a memory instance and store it.
        
        Args:
            memory_config: Memory configuration
            
        Returns:
            MemoryConfig: Memory configuration with instance
        """
        if memory_config.name in self._memory_configs:
            existing_config = self._memory_configs[memory_config.name]
            if existing_config.instance is not None:
                return existing_config
        
        # Create new memory instance
        try:
            # cls should already be loaded (either from registry or from code)
            if memory_config.cls is None:
                raise ValueError(f"Cannot create memory {memory_config.name}: no class provided. Class should be loaded during initialization.")
            
            # Instantiate memory instance
            memory_instance = memory_config.cls(**memory_config.config) if memory_config.config else memory_config.cls()
            
            # Initialize memory if it has an initialize method
            if hasattr(memory_instance, "initialize"):
                await memory_instance.initialize()

            # Register with permission manager
            permission_manager.register(
                entity_name=memory_config.name,
                mode=PermissionMode(getattr(memory_instance, "permission_mode", "workspace_write")),
            )

            memory_config.instance = memory_instance

            # Store memory metadata
            self._memory_configs[memory_config.name] = memory_config

            logger.info(f"| 🔧 Memory {memory_config.name} created and stored")
            
            return memory_config
        except Exception as e:
            logger.error(f"| ❌ Failed to create memory {memory_config.name}: {e}")
            raise
    
    async def restore(self, memory_name: str, version: str, auto_initialize: bool = True) -> Optional[MemoryConfig]:
        """Restore a specific version of a memory system from history
        
        Args:
            memory_name: Name of the memory system
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored memory
            
        Returns:
            MemoryConfig of the restored version, or None if not found
        """
        # Look up version from dict-based history (O(1) lookup)
        version_config = None
        if memory_name in self._memory_history_versions:
            version_config = self._memory_history_versions[memory_name].get(version)
        
        if version_config is None:
            logger.warning(f"| ⚠️ Version {version} not found for memory {memory_name}")
            return None
        
        # Create a copy to avoid modifying the history
        restored_config = MemoryConfig(**version_config.model_dump())
        
        # Set as current active config
        self._memory_configs[memory_name] = restored_config
        
        # Update version manager current version
        version_history = await version_manager.get_version_history("memory", memory_name)
        if version_history:
            # Check if version exists in version history, if not register it
            if version not in version_history.versions:
                await version_manager.register_version("memory", memory_name, version)
            version_history.current_version = version
        else:
            # If version history doesn't exist, register the version first
            await version_manager.register_version("memory", memory_name, version)
        
        # Initialize if requested
        if auto_initialize and restored_config.cls is not None:
            await self.build(restored_config)
        
        # Persist to JSON (current_version changes)
        
        logger.info(f"| 🔄 Restored memory {memory_name} to version {version}")
        return restored_config
    
    async def cleanup(self):
        """Cleanup all active memory systems."""
        try:
            # Clear all memory configs and version history
            self._memory_configs.clear()
            self._memory_history_versions.clear()
                
            logger.info("| 🧹 Memory context manager cleaned up")
            
        except Exception as e:
            logger.error(f"| ❌ Error during memory context manager cleanup: {e}")
            
    async def start_session(self,
                            memory_name: str,
                            agent_name: Optional[str] = None,
                            task_id: Optional[str] = None,
                            description: Optional[str] = None,
                            ctx: SessionContext = None,
                            **kwargs) -> str:
        """Start a memory session (delegates to memory system instance).

        Args:
            memory_name: Name of the memory system
            agent_name: Optional agent name
            task_id: Optional task ID
            description: Optional description
            ctx: Memory context

        Returns:
            Session ID
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name, agent_name=agent_name, task_id=task_id)
        instance = await self.get(memory_name)
        if instance is None:
            raise ValueError(f"Memory system '{memory_name}' not found")
        return await instance.start_session(agent_name=agent_name, task_id=task_id, description=description, ctx=memory_ctx, **kwargs)

    async def add_event(self,
                        memory_name: str,
                        step_number: int,
                        event_type: Any,
                        data: Any,
                        agent_name: str,
                        task_id: Optional[str] = None,
                        ctx: SessionContext = None,
                        **kwargs):
        """Add an event to memory (delegates to memory system instance).

        Args:
            memory_name: Name of the memory system
            step_number: Step number
            event_type: Event type
            data: Event data
            agent_name: Agent name
            task_id: Optional task ID
            ctx: Memory context
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name, agent_name=agent_name, task_id=task_id)
        instance = await self.get(memory_name)
        if instance is None:
            raise ValueError(f"Memory system '{memory_name}' not found")
        return await instance.add_event(step_number, event_type, data, agent_name, task_id, ctx=memory_ctx, **kwargs)

    async def end_session(self, memory_name: str,
                          ctx: SessionContext = None,
                          **kwargs):
        """End a memory session (delegates to memory system instance).

        Args:
            memory_name: Name of the memory system
            ctx: Memory context
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name)
        instance = await self.get(memory_name)
        if instance is None:
            raise ValueError(f"Memory system '{memory_name}' not found")
        return await instance.end_session(ctx=memory_ctx, **kwargs)

    async def get_session_info(self, memory_name: str,
                               ctx: SessionContext = None,
                               **kwargs):
        """Get session info (delegates to memory system instance).

        Args:
            memory_name: Name of the memory system
            ctx: Memory context

        Returns:
            SessionInfo or None
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name)
        instance = await self.get(memory_name)
        if instance is None:
            raise ValueError(f"Memory system '{memory_name}' not found")
        return await instance.get_session_info(ctx=memory_ctx, **kwargs)

    async def clear_session(self,
                            memory_name: str,
                            ctx: SessionContext = None,
                            **kwargs):
        """Clear a memory session (delegates to memory system instance).

        Args:
            memory_name: Name of the memory system
            ctx: Memory context
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name)
        instance = await self.get(memory_name)
        if instance is None:
            raise ValueError(f"Memory system '{memory_name}' not found")
        return await instance.clear_session(ctx=memory_ctx, **kwargs)

    async def get_state(self,
                        memory_name: str,
                        n: Optional[int] = None,
                        ctx: SessionContext = None,
                        **kwargs) -> Dict[str, Any]:
        """Get memory state (events, summaries, insights) for a memory system.

        Args:
            memory_name: Name of the memory system
            n: Number of items to retrieve. If None, returns all items.
            ctx: Memory context

        Returns:
            Dictionary containing 'events', 'summaries', and 'insights'
        """
        if ctx is None:
            ctx = SessionContext()
        memory_ctx = MemoryContext.from_session(ctx, memory_name=memory_name)

        memory_info = await self.get_info(memory_name)

        version = memory_info.version
        memory_instance = memory_info.instance
        logger.info(f"| ✅ Using memory {memory_name}@{version}")
        
        # Get events, summaries, and insights from memory instance
        events = await memory_instance.get_event(n=n, ctx=memory_ctx, **kwargs)
        summaries = await memory_instance.get_summary(n=n, ctx=memory_ctx, **kwargs)
        insights = await memory_instance.get_insight(n=n, ctx=memory_ctx, **kwargs)
        
        return {
            "events": events,
            "summaries": summaries,
            "insights": insights
        }
