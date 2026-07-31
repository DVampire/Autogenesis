"""Agent Context Manager for managing agent lifecycle and resources with lazy loading."""
import asyncio
import os
from asyncio_atexit import register as async_atexit_register
from typing import Any, Dict, List, Type, Optional, Union, Tuple, TYPE_CHECKING
from datetime import datetime
import inflection
import json
from pydantic import BaseModel, ConfigDict, Field


from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.utils import (
    assemble_workspace_path,
    gather_with_concurrency,
    file_lock
)
from autogenesis.agent.types import Agent, AgentConfig, AgentContext
from autogenesis.version import version_manager
from autogenesis.dynamic import dynamic_manager
from autogenesis.registry import AGENT
from autogenesis.permission import permission_manager, PermissionMode


class AgentContextManager(BaseModel):
    """Global context manager for all agents with lazy loading and version history."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="The base directory to use for the agents")

    def __init__(
        self,
        base_dir: Optional[str] = None,
        model_name: str = "openrouter/gemini-3-flash-preview",
        **kwargs: Any,
    ):
        """Initialize the agent context manager.

        Args:
            base_dir: Base directory for storing agent data
            model_name: The model name used for the agents
        """
        super().__init__(**kwargs)

        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "agent"))
        logger.info(f"| 📁 Agent context manager base directory: {self.base_dir}.")
        logger.info(f"| 📁 Agent context manager.")

        # Current active configs (latest version)
        self._agent_configs: Dict[str, AgentConfig] = {}
        # Agent version history, e.g., {"agent_name": {"1.0.0": AgentConfig, ...}}
        self._agent_history_versions: Dict[str, Dict[str, AgentConfig]] = {}

        self.model_name = model_name

        self._cleanup_registered = False
        self._variables_lock = asyncio.Lock()  # Lock for get/set trainable variables

    def _prepare_instance_config(
        self,
        agent_cls: Type[Agent],
        instance_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a private config copy with a deterministic workspace fallback.

        Agent ``base_dir`` is intentionally required at the type layer.  Registry
        discovery, however, may run without a class-specific config file (for
        example in schema inspection and tests).  The manager owns that lifecycle
        concern, so it supplies an isolated directory without weakening Agent's
        constructor contract.
        """
        prepared = dict(instance_config or {})
        agent_name = agent_cls.model_fields["name"].default
        prepared.setdefault("base_dir", os.path.join(self.base_dir, agent_name))
        return prepared

    async def initialize(self, agent_names: Optional[List[str]] = None) -> None:
        """Initialize the agent context manager and all registered agents."""

        # Register agent-related symbols for auto-injection in dynamic code
        dynamic_manager.register_symbol("AGENT", AGENT)
        dynamic_manager.register_symbol("Agent", Agent)
        dynamic_manager.register_symbol("AgentConfig", AgentConfig)

        # Register agent context provider for automatic import injection
        def agent_context_provider():
            """Supply the agent symbols auto-injected into dynamically compiled code."""
            return {
                "AGENT": AGENT,
                "Agent": Agent,
                "AgentConfig": AgentConfig,
            }

        dynamic_manager.register_context_provider("agent", agent_context_provider)

        # Load agents from AGENT registry
        agent_configs: Dict[str, AgentConfig] = {}
        registry_agent_configs: Dict[str, AgentConfig] = await self._load_from_registry()
        agent_configs.update(registry_agent_configs)

        # Load agents from code JSON (including older versions / dynamic agents)
        code_agent_configs: Dict[str, AgentConfig] = {}

        # Merge code configs with registry configs, only override if code version is strictly greater
        for agent_name, code_config in code_agent_configs.items():
            if agent_name in agent_configs:
                registry_config = agent_configs[agent_name]
                if (
                    version_manager.compare_versions(
                        code_config.version, registry_config.version
                    )
                    > 0
                ):
                    logger.info(
                        f"| 🔄 Overriding agent {agent_name} from registry "
                        f"(v{registry_config.version}) with code version (v{code_config.version})"
                    )
                    agent_configs[agent_name] = code_config
                else:
                    logger.info(
                        f"| 📌 Keeping agent {agent_name} from registry (v{registry_config.version}), "
                        f"code version (v{code_config.version}) is not greater"
                    )
                    # If versions are equal, update the history with registry config (which has real class, not dynamic)
                    if version_manager.compare_versions(code_config.version, registry_config.version) == 0:
                        # Replace the code config in history with registry config to preserve real class reference
                        if agent_name in self._agent_history_versions:
                            self._agent_history_versions[agent_name][registry_config.version] = registry_config
            else:
                agent_configs[agent_name] = code_config

        # Filter agents by names if provided
        if agent_names is not None:
            agent_configs = {name: agent_configs[name] for name in agent_names if name in agent_configs}

        # Build all agents concurrently with a concurrency limit
        names = list(agent_configs.keys())
        tasks = [self.build(agent_configs[name]) for name in names]
        results = await gather_with_concurrency(
            tasks, max_concurrency=10, return_exceptions=True
        )

        for agent_name, result in zip(names, results):
            if isinstance(result, Exception):
                logger.error(f"| ❌ Failed to initialize agent {agent_name}: {result}")
                continue
            self._agent_configs[agent_name] = result
            logger.info(f"| 🎮 Agent {agent_name} initialized")

        # Save agent configs to json file
        # Save contract to file

        # Register async cleanup callback
        async_atexit_register(self.cleanup)
        self._cleanup_registered = True

        logger.info("| ✅ Agents initialization completed")

    async def _load_from_registry(self) -> Dict[str, AgentConfig]:
        """Load agents from AGENT registry."""

        agent_configs: Dict[str, AgentConfig] = {}

        async def register_agent_class(agent_cls: Type[Agent]):
            """Register an agent class synchronously.
            
            Args:
                agent_cls: Agent class to register
            """
            try:
                # Get agent config from global config
                agent_config_key = inflection.underscore(agent_cls.__name__)
                agent_config_dict = getattr(config, agent_config_key, {})
                agent_enable_evolving = agent_config_dict.get("enable_evolving", False) if agent_config_dict and "enable_evolving" in agent_config_dict else False
                
                # Get agent properties from agent class
                agent_name = agent_cls.model_fields['name'].default
                agent_description = agent_cls.model_fields['description'].default
                agent_metadata = agent_cls.model_fields['metadata'].default
                agent_type = agent_cls.model_fields['agent_type'].default
                
                # Get or generate version from version_manager
                agent_version = await version_manager.get_version("agent", agent_name)
                
                # Get full module source code
                agent_code = dynamic_manager.get_full_module_source(agent_cls)
                
                agent_parameters = dynamic_manager.get_parameters(agent_cls)
                agent_function_calling = dynamic_manager.build_function_calling(agent_name, agent_description, agent_parameters)
                agent_text = dynamic_manager.build_text_representation(agent_name, agent_description, agent_parameters)
                agent_args_schema = dynamic_manager.build_args_schema(agent_name, agent_parameters)
                
                # Create agent config (AgentConfig.id is auto-incremented internally if needed)
                agent_config = AgentConfig(
                    name=agent_name,
                    description=agent_description,
                    version=agent_version,
                    enable_evolving=agent_enable_evolving,
                    cls=agent_cls,
                    config=agent_config_dict,
                    instance=None,
                    function_calling=agent_function_calling,
                    text=agent_text,
                    args_schema=agent_args_schema,
                    metadata=agent_metadata,
                    agent_type=agent_type,
                    code=agent_code,
                )
                
                # Store agent config
                agent_configs[agent_name] = agent_config
                
                # Store in version history (by version string)
                if agent_name not in self._agent_history_versions:
                    self._agent_history_versions[agent_name] = {}
                self._agent_history_versions[agent_name][agent_version] = agent_config
                
                # Register version to version manager
                await version_manager.register_version("agent", agent_name, agent_version)
                
                logger.info(f"| 📝 Registered agent: {agent_name} ({agent_cls.__name__})")
                
            except Exception as e:
                logger.error(f"| ❌ Failed to register agent class {agent_cls.__name__}: {e}")
                raise

        import autogenesis.agent  # noqa: F401

        agent_classes = list(AGENT._module_dict.values())
        logger.info(f"| 🔍 Discovering {len(agent_classes)} agents from AGENT registry")

        tasks = [register_agent_class(agent_cls) for agent_cls in agent_classes]
        results = await gather_with_concurrency(
            tasks, max_concurrency=10, return_exceptions=True
        )
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(
            f"| ✅ Discovered and registered {success_count}/{len(agent_classes)} agents from AGENT registry"
        )

        return agent_configs

    async def build(self, agent_config: AgentConfig) -> AgentConfig:
        """Create an agent instance and store it.
        
        Args:
            agent_config: Agent configuration
            
        Returns:
            AgentConfig: Agent configuration with instance
        """
        if agent_config.name in self._agent_configs:
            existing_config = self._agent_configs[agent_config.name]
            if existing_config.instance is not None:
                return existing_config
        
        # Create new agent instance
        try:
            # cls should already be loaded (either from registry or from code)
            if agent_config.cls is None:
                raise ValueError(f"Cannot create agent {agent_config.name}: no class provided. Class should be loaded during initialization.")
            
            # Instantiate with a manager-owned workspace when no explicit one was
            # declared. Keep the normalized config so rebuilds are deterministic.
            agent_config.config = self._prepare_instance_config(agent_config.cls, agent_config.config)
            agent_instance = agent_config.cls(**agent_config.config)
            
            # Initialize agent if it has an initialize method
            if hasattr(agent_instance, "initialize"):
                await agent_instance.initialize()

            # Register with permission manager
            permission_manager.register(
                entity_name=agent_instance.name,
                mode=PermissionMode(agent_instance.permission_mode),
            )

            agent_config.instance = agent_instance

            # Store agent metadata
            self._agent_configs[agent_config.name] = agent_config

            logger.info(f"| 🔧 Agent {agent_config.name} created and stored")
            
            return agent_config
        except Exception as e:
            logger.error(f"| ❌ Failed to create agent {agent_config.name}: {e}")
            raise

    async def register(
        self,
        agent_cls: Type[Agent],
        agent_config_dict: Optional[Dict[str, Any]] = None,
        override: bool = False,
        version: Optional[str] = None,
    ) -> AgentConfig:
        """Register an agent class.

        This will:
        - Create (or reuse) an agent instance
        - Create an `AgentConfig`
        - Store it as the current config and append to version history
        - Register the version in `version_manager` and FAISS index
        """
        
        try:
            if agent_config_dict is None:
                # Fallback to global config by class name
                agent_config_key = inflection.underscore(agent_cls.__name__)
                agent_config_dict = getattr(config, agent_config_key, {})
            
            agent_config_dict = self._prepare_instance_config(agent_cls, agent_config_dict)

            # Instantiate agent immediately (register is a runtime operation)
            try:
                agent_instance = agent_cls(**agent_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create agent instance for {agent_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate agent {agent_cls.__name__} with provided config: {e}")
            
            agent_name = agent_instance.name
            agent_description = agent_instance.description
            agent_metadata = agent_instance.metadata
            agent_enable_evolving = agent_config_dict.get("enable_evolving", agent_instance.enable_evolving) if agent_config_dict and "enable_evolving" in agent_config_dict else agent_instance.enable_evolving

            # Register with permission manager
            permission_manager.register(
                entity_name=agent_name,
                mode=PermissionMode(agent_instance.permission_mode),
            )

            # Get or generate version from version_manager
            if version is None:
                agent_version = await version_manager.get_version("agent", agent_name)
            else:
                agent_version = version
                
            # Get agent code
            agent_code = dynamic_manager.get_source_code(agent_cls)
            if not agent_code:
                logger.warning(f"| ⚠️ Agent {agent_name} is dynamic but source code cannot be extracted")
            
            # Get agent parameters
            agent_parameters = dynamic_manager.get_parameters(agent_cls)
            agent_function_calling = dynamic_manager.build_function_calling(agent_name, agent_description, agent_parameters)
            agent_text = dynamic_manager.build_text_representation(agent_name, agent_description, agent_parameters)
            agent_args_schema = dynamic_manager.build_args_schema(agent_name, agent_parameters)
            
            # --- Build AgentConfig ---
            agent_config = AgentConfig(
                name=agent_name,
                description=agent_description,
                metadata=agent_metadata,
                version=agent_version,
                enable_evolving=agent_enable_evolving,
                agent_type=agent_instance.agent_type,
                cls=agent_cls,
                config=agent_config_dict or {},
                instance=agent_instance,
                function_calling=agent_function_calling,
                text=agent_text,
                args_schema=agent_args_schema,
                code=agent_code,
            )
            
            # --- Persist current config and history ---
            self._agent_configs[agent_name] = agent_config
            
            # Store in dict-based history (for quick lookup by version)
            if agent_name not in self._agent_history_versions:
                self._agent_history_versions[agent_name] = {}
            self._agent_history_versions[agent_name][agent_config.version] = agent_config
            
            # Register version in version manager
            await version_manager.register_version("agent", agent_name, agent_config.version)
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 📝 Registered agent config: {agent_name}: {agent_config.version}")
            return agent_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to register agent: {e}")
            raise

    async def get(self, agent_name: str) -> Optional[Agent]:
        """Get agent configuration by name
        
        Args:
            agent_name: Agent name
            
        Returns:
            Agent: Agent instance or None if not found
        """
        agent_config = self._agent_configs.get(agent_name)
        if agent_config is None:
            return None
        return agent_config.instance if agent_config.instance is not None else None
    
    async def get_info(self, agent_name: str) -> Optional[AgentConfig]:
        """Get agent info by name
        
        Args:
            agent_name: Agent name
            
        Returns:
            AgentConfig: Agent info or None if not found
        """
        return self._agent_configs.get(agent_name)
    
    async def list(self) -> List[str]:
        """Get list of registered agents
        
        Returns:
            List[str]: List of agent names
        """
        return [name for name in self._agent_configs.keys()]

    async def update(
        self,
        agent_cls: Type[Agent],
        agent_config_dict: Optional[Dict[str, Any]] = None,
        new_version: Optional[str] = None,
        description: Optional[str] = None,
        code: Optional[str] = None,
    ) -> AgentConfig:
        """Update an existing agent with new configuration and create a new version
        
        Args:
            agent_cls: New agent class with updated implementation
            agent_config_dict: Configuration dict for agent initialization
                   If None, will try to get from global config
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string. If provided, uses this instead of extracting from agent_cls.
                  This is useful when agent_cls is dynamically created from code string.
            
        Returns:
            AgentConfig: Updated agent configuration
        """
        try:
            if agent_config_dict is None:
                # Fallback to global config by class name
                agent_config_key = inflection.underscore(agent_cls.__name__)
                agent_config_dict = getattr(config, agent_config_key, {})
            
            agent_config_dict = self._prepare_instance_config(agent_cls, agent_config_dict)

            # Instantiate agent immediately (update is a runtime operation)
            try:
                agent_instance = agent_cls(**agent_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create agent instance for {agent_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate agent {agent_cls.__name__} with provided config: {e}")
            
            agent_name = agent_instance.name
            
            # Check if agent exists
            original_config = self._agent_configs.get(agent_name)
            if original_config is None:
                raise ValueError(f"Agent {agent_name} not found. Use register() to register a new agent.")
            
            agent_description = agent_instance.description
            agent_metadata = agent_instance.metadata
            agent_enable_evolving = agent_config_dict.get("enable_evolving", agent_instance.enable_evolving) if agent_config_dict else agent_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                # Get current version from version_manager and generate next patch version
                new_version = await version_manager.generate_next_version("agent", agent_name, "patch")
            
            # Get agent code - use provided code if available (for dynamically created classes)
            if code is not None:
                agent_code = code
            else:
                agent_code = dynamic_manager.get_source_code(agent_cls)
                if not agent_code:
                    logger.warning(f"| ⚠️ Agent {agent_name} is dynamic but source code cannot be extracted")
            
            # Get agent parameters and build properties using dynamic_manager methods
            agent_parameters = dynamic_manager.get_parameters(agent_cls)
            agent_function_calling = dynamic_manager.build_function_calling(agent_name, agent_description, agent_parameters)
            agent_text = dynamic_manager.build_text_representation(agent_name, agent_description, agent_parameters)
            agent_args_schema = dynamic_manager.build_args_schema(agent_name, agent_parameters)
            
            # --- Build AgentConfig ---
            updated_config = AgentConfig(
                name=agent_name,  # Keep same name
                description=agent_description,
                metadata=agent_metadata,
                version=new_version,
                enable_evolving=agent_enable_evolving,
                agent_type=agent_instance.agent_type,
                cls=agent_cls,
                config=agent_config_dict or {},
                instance=agent_instance,
                function_calling=agent_function_calling,
                text=agent_text,
                args_schema=agent_args_schema,
                code=agent_code,
            )
            
            # Update the agent config (replaces current version)
            self._agent_configs[agent_name] = updated_config
            
            # Store in version history
            if agent_name not in self._agent_history_versions:
                self._agent_history_versions[agent_name] = {}
            self._agent_history_versions[agent_name][updated_config.version] = updated_config
            
            # Register new version record to version manager
            await version_manager.register_version(
                "agent", 
                agent_name, 
                new_version,
                description=description or f"Updated from {original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 🔄 Updated agent {agent_name} from v{original_config.version} to v{new_version}")
            return updated_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to update agent: {e}")
            raise

    async def copy(
        self,
        agent_name: str,
        new_name: Optional[str] = None,
        new_version: Optional[str] = None,
        new_config: Optional[Dict[str, Any]] = None,
    ) -> AgentConfig:
        """Copy an existing agent configuration
        
        Args:
            agent_name: Name of the agent to copy
            new_name: New name for the copied agent. If None, uses original name.
            new_version: New version for the copied agent. If None, increments version.
            new_config: New configuration dict for the copied agent. If None, uses original config.
            
        Returns:
            AgentConfig: New agent configuration
        """
        try:
            original_config = self._agent_configs.get(agent_name)
            if original_config is None:
                raise ValueError(f"Agent {agent_name} not found")
            
            if original_config.cls is None:
                raise ValueError(f"Cannot copy agent {agent_name}: no class provided")
            
            # Determine new name
            if new_name is None:
                new_name = agent_name
            
            # Prepare config dict (merge original config with new config)
            agent_config_dict = original_config.config.copy() if original_config.config else {}
            if new_config:
                # Merge new config into original config
                agent_config_dict.update(new_config)
            
            # Instantiate agent instance (copy is a runtime operation)
            try:
                agent_instance = original_config.cls(**agent_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create agent instance for {original_config.cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate agent {original_config.cls.__name__} with provided config: {e}")
            
            # Apply name override if provided (after instantiation)
            if new_name != agent_name:
                agent_instance.name = new_name
            
            agent_description = agent_instance.description
            agent_metadata = agent_instance.metadata
            agent_enable_evolving = agent_config_dict.get("enable_evolving", agent_instance.enable_evolving) if agent_config_dict and "enable_evolving" in agent_config_dict else agent_instance.enable_evolving
            
            # Determine new version from version_manager
            if new_version is None:
                if new_name == agent_name:
                    # If copying with same name, get next version from version_manager
                    new_version = await version_manager.generate_next_version("agent", new_name, "patch")
                else:
                    # If copying with different name, get or generate version for new name
                    new_version = await version_manager.get_version("agent", new_name)
            
            # Get agent code
            agent_code = dynamic_manager.get_source_code(original_config.cls)
            if not agent_code:
                logger.warning(f"| ⚠️ Agent {new_name} is dynamic but source code cannot be extracted")
            
            # Get agent parameters and build properties using dynamic_manager methods
            agent_parameters = dynamic_manager.get_parameters(original_config.cls)
            agent_function_calling = dynamic_manager.build_function_calling(new_name, agent_description, agent_parameters)
            agent_text = dynamic_manager.build_text_representation(new_name, agent_description, agent_parameters)
            agent_args_schema = dynamic_manager.build_args_schema(new_name, agent_parameters)
            
            # --- Build AgentConfig ---
            new_agent_config = AgentConfig(
                name=new_name,
                description=agent_description,
                metadata=agent_metadata,
                version=new_version,
                enable_evolving=agent_enable_evolving,
                agent_type=agent_instance.agent_type,
                cls=original_config.cls,
                config=agent_config_dict,
                instance=agent_instance,
                function_calling=agent_function_calling,
                text=agent_text,
                args_schema=agent_args_schema,
                code=agent_code,
            )
            
            # Register new agent
            self._agent_configs[new_name] = new_agent_config
            
            # Store in version history
            if new_name not in self._agent_history_versions:
                self._agent_history_versions[new_name] = {}
            self._agent_history_versions[new_name][new_version] = new_agent_config
            
            # Register version record to version manager
            await version_manager.register_version(
                "agent", 
                new_name, 
                new_version,
                description=f"Copied from {agent_name}@{original_config.version}"
            )
            
            # Persist to JSON
            # Save contract to file
            
            logger.info(f"| 📋 Copied agent {agent_name}@{original_config.version} to {new_name}@{new_version}")
            return new_agent_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to copy agent: {e}")
            raise

    async def unregister(self, agent_name: str) -> bool:
        """Unregister an agent
        
        Args:
            agent_name: Name of the agent to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        if agent_name not in self._agent_configs:
            logger.warning(f"| ⚠️ Agent {agent_name} not found")
            return False
        
        agent_config = self._agent_configs[agent_name]
        
        # Remove from configs
        del self._agent_configs[agent_name]

        # Persist to JSON after unregister
        # Save contract to file
        
        logger.info(f"| 🗑️ Unregistered agent {agent_name}@{agent_config.version}")
        return True

    async def restore(
        self, agent_name: str, version: str, auto_initialize: bool = True
    ) -> Optional[AgentConfig]:
        """Restore a specific version of an agent from history
        
        Args:
            agent_name: Name of the agent
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored agent
            
        Returns:
            AgentConfig of the restored version, or None if not found
        """
        # Look up version from dict-based history (O(1) lookup)
        version_config = None
        if agent_name in self._agent_history_versions:
            version_config = self._agent_history_versions[agent_name].get(version)
        
        if version_config is None:
            logger.warning(f"| ⚠️ Version {version} not found for agent {agent_name}")
            return None
        
        # Create a copy to avoid modifying the history
        restored_config = AgentConfig(**version_config.model_dump())
        
        # Set as current active config
        self._agent_configs[agent_name] = restored_config
        
        # Update version manager current version
        version_history = await version_manager.get_version_history("agent", agent_name)
        if version_history:
            # Check if version exists in version history, if not register it
            if version not in version_history.versions:
                await version_manager.register_version("agent", agent_name, version)
            version_history.current_version = version
        else:
            # If version history doesn't exist, register the version first
            await version_manager.register_version("agent", agent_name, version)
        
        # Initialize if requested
        if auto_initialize and restored_config.cls is not None:
            await self.build(restored_config)
        
        # Persist to JSON (current_version changes)
        
        logger.info(f"| 🔄 Restored agent {agent_name} to version {version}")
        return restored_config
    
    async def cleanup(self):
        """Cleanup all active agents."""
        try:
            # Clear all agent configs and version history
            self._agent_configs.clear()
            self._agent_history_versions.clear()
                
            logger.info("| 🧹 Agent context manager cleaned up")
            
        except Exception as e:
            logger.error(f"| ❌ Error during agent context manager cleanup: {e}")
            
    async def __call__(self, 
                       name: str, 
                       input: Dict[str, Any], 
                       ctx: AgentContext = None, 
                       **kwargs) -> Any:
        """Call an agent by name

        Args:
            name: Agent name
            input: Input for the agent
            ctx: Agent context
            **kwargs: Additional keyword arguments forwarded to the agent
        Returns:
            Agent result
        """
        agent_info = await self.get_info(name)

        agent_args = dict(ctx=ctx, **kwargs)

        version = agent_info.version
        agent_instance = agent_info.instance
        logger.info(f"| ✅ Using agent {name}@{version}")

        from autogenesis.runtime.server import runtime_manager
        return await runtime_manager.invoke(agent_instance, **input, **agent_args)
