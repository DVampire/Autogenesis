"""Environment Context Manager for managing environment lifecycle and resources with lazy loading."""

import os
import re
import json
import inspect
import inflection
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Type, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field

from asyncio_atexit import register as async_atexit_register

from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.version import version_manager
from autogenesis.utils import assemble_workspace_path, gather_with_concurrency
from autogenesis.utils.file_utils import file_lock
from autogenesis.environment.types import Environment, EnvironmentConfig, ActionConfig, EnvironmentContext
from autogenesis.sandbox import SandboxServerManager, default_domain
from autogenesis.dynamic import dynamic_manager
from autogenesis.registry import ENVIRONMENT

class EnvironmentContextManager(BaseModel):
    """Global context manager for all environments with lazy loading support."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="The base directory to use for the environments")
            
    def __init__(self,
                 base_dir: Optional[str] = None,
                 **kwargs):
        """Initialize the environment context manager.

        Args:
            base_dir: Base directory for storing environment data
        """
        super().__init__(**kwargs)
        
        # Set up paths
        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            base_root = config.log_root if hasattr(config, "log_root") and config.get("log_root") else config.workspace_root
            self.base_dir = assemble_workspace_path(os.path.join(base_root, "environment"))
        logger.info(f"| 📁 Environment context manager base directory: {self.base_dir}.")    
        logger.info(f"| 📁 Environment context manager.")

        self._environment_configs: Dict[str, EnvironmentConfig] = {}  # Current active configs (latest version)
        # Environment version history, e.g., {"env_name": {"1.0.0": EnvironmentConfig, "1.0.1": EnvironmentConfig}}
        self._environment_history_versions: Dict[str, Dict[str, EnvironmentConfig]] = {}

        # Daemon domain comes from the port manager (preferring OPENSANDBOX, else a
        # free port) rather than a hard-coded 8080, so it can't collide on a shared host.
        self._sandbox_server = SandboxServerManager(domain=default_domain())
        self._cleanup_registered = False
        
    async def initialize(self, env_names: Optional[List[str]] = None):
        """Initialize the environment context manager."""

        await version_manager.initialize()

        # Register environment-related symbols for auto-injection in dynamic code
        dynamic_manager.register_symbol("ENVIRONMENT", ENVIRONMENT)
        dynamic_manager.register_symbol("Environment", Environment)
        dynamic_manager.register_symbol("EnvironmentConfig", EnvironmentConfig)
        dynamic_manager.register_symbol("ActionConfig", ActionConfig)
        
        # Register environment context provider for automatic import injection
        def environment_context_provider():
            """Provide environment-related imports for dynamic environment classes."""
            return {
                "ENVIRONMENT": ENVIRONMENT,
                "Environment": Environment,
                "EnvironmentConfig": EnvironmentConfig,
                "ActionConfig": ActionConfig,
            }
        dynamic_manager.register_context_provider("environment", environment_context_provider)
        
        # Load environments from ENVIRONMENT registry
        env_configs = {}
        registry_env_configs: Dict[str, EnvironmentConfig] = await self._load_from_registry()
        env_configs.update(registry_env_configs)
        
        # Load environments from code
        code_configs: Dict[str, EnvironmentConfig] = {}
        
        # Merge code configs with registry configs, only override if code version is strictly greater
        for env_name, code_config in code_configs.items():
            if env_name in env_configs:
                registry_config = env_configs[env_name]
                # Compare versions: only override if code version is strictly greater
                if version_manager.compare_versions(code_config.version, registry_config.version) > 0:
                    logger.info(f"| 🔄 Overriding environment {env_name} from registry (v{registry_config.version}) with code version (v{code_config.version})")
                    env_configs[env_name] = code_config
                else:
                    logger.info(f"| 📌 Keeping environment {env_name} from registry (v{registry_config.version}), code version (v{code_config.version}) is not greater")
                    # If versions are equal, update the history with registry config (which has real class, not dynamic)
                    if version_manager.compare_versions(code_config.version, registry_config.version) == 0:
                        # Replace the code config in history with registry config to preserve real class reference
                        if env_name in self._environment_history_versions:
                            self._environment_history_versions[env_name][registry_config.version] = registry_config
            else:
                # New environment from code, add it
                env_configs[env_name] = code_config
        
        # Filter environments by names if provided
        if env_names is not None:
            env_configs = {name: env_configs[name] for name in env_names if name in env_configs}
        
        # Start opensandbox-server once if any environment requires it
        await self._ensure_sandbox_server(env_configs)

        # Build all environments concurrently with a concurrency limit
        env_names_list = list(env_configs.keys())
        tasks = [
            self.build(env_configs[name]) for name in env_names_list
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)

        for env_name, result in zip(env_names_list, results):
            if isinstance(result, Exception):
                logger.error(f"| ❌ Failed to initialize environment {env_name}: {result}")
                continue
            self._environment_configs[env_name] = result
            logger.info(f"| 🎮 Environment {env_name} initialized")
        
        # Save environment configs to json file
        # Save contract to file
        
        # Register cleanup callback
        async_atexit_register(self.cleanup)
        self._cleanup_registered = True
        
        logger.info(f"| ✅ Environments initialization completed")
    
    # ------------------------------------------------------------------
    # ENVIRONMENT.md parsing (rules + docs live in the md, not in code)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
        """Split YAML frontmatter (between --- delimiters) from the markdown body."""
        pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        match = pattern.match(text)
        if not match:
            return {}, text
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as e:
            logger.warning(f"| ⚠️ Failed to parse ENVIRONMENT.md frontmatter: {e}")
            frontmatter = {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}
        return frontmatter, text[match.end():]

    def _load_environment_md(self, env_cls: Type[Environment]) -> Optional[Tuple[Dict[str, Any], str, str]]:
        """Locate and parse the ENVIRONMENT.md that sits next to an environment class.

        Returns (frontmatter, body, md_path) or None if the class has no source file
        or no ENVIRONMENT.md beside it (e.g. dynamically generated environments).
        """
        try:
            env_file = inspect.getfile(env_cls)
        except (TypeError, OSError):
            env_file = getattr(env_cls, "__source_file__", None)
        if not env_file:
            return None
        md_path = Path(env_file).parent / "ENVIRONMENT.md"
        if not md_path.exists():
            return None
        try:
            frontmatter, body = self._parse_frontmatter(md_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"| ⚠️ Failed to read {md_path}: {e}")
            return None
        return frontmatter, body.strip(), str(md_path)

    async def _load_from_registry(self):
        """Load environments from ENVIRONMENT registry."""
        
        env_configs: Dict[str, EnvironmentConfig] = {}
        
        async def register_environment_class(env_cls: Type[Environment]):
            """Register an environment class.
            
            Args:
                env_cls: Environment class to register
            """
            try:
                env_config_key = inflection.underscore(env_cls.__name__)
                env_config_dict= config.get(env_config_key, {})
                env_enable_evolving = env_config_dict.get("enable_evolving", False) if env_config_dict and "enable_evolving" in env_config_dict else False
                
                # Get environment properties from environment class
                env_name = env_cls.model_fields['name'].default
                env_description = env_cls.model_fields['description'].default
                env_metadata = env_cls.model_fields['metadata'].default

                # Rules + docs come from the ENVIRONMENT.md beside the class (not get_rules()).
                env_rules = ""
                md = self._load_environment_md(env_cls)
                if md:
                    frontmatter, body, _ = md
                    env_description = frontmatter.get("description", env_description)
                    env_rules = body
                else:
                    logger.warning(f"| ⚠️ No ENVIRONMENT.md found for environment '{env_name}'; rules will be empty")

                # Get or generate version from version_manager
                env_version = await version_manager.get_version("environment", env_name)
                
                # Get full module source code
                env_code = dynamic_manager.get_full_module_source(env_cls)
                
                # Build actions from environment class
                env_actions = {}
                for attr_name in dir(env_cls):
                    attr = getattr(env_cls, attr_name)
                    if hasattr(attr, '_action_name'):
                        action_name = getattr(attr, '_action_name')
                        action_description = getattr(attr, '_action_description', '')
                        action_function = getattr(attr, '_action_function', None)
                        action_metadata = getattr(attr, '_action_metadata', {})
                        
                        action_version = await version_manager.get_version("action", action_name)
                        
                        action_code = dynamic_manager.get_source_code(attr)
                        if not action_code:
                            logger.warning(f"| ⚠️ Action {action_name} is dynamic but source code cannot be extracted")
                        
                        action_parameters = dynamic_manager.get_parameters(action_function)
                        action_function_calling = dynamic_manager.build_function_calling(action_name, action_description, action_parameters)
                        action_text = dynamic_manager.build_text_representation(action_name, action_description, action_parameters)
                        action_args_schema = dynamic_manager.build_args_schema(action_name, action_parameters)
                        
                        action_config = ActionConfig(
                            env_name=env_name,
                            name=action_name,
                            description=action_description,
                            function=action_function,
                            metadata=action_metadata,
                            version=action_version,
                            code=action_code,
                            function_calling=action_function_calling,
                            text=action_text,
                            args_schema=action_args_schema,
                        )
                        
                        env_actions[action_name] = action_config
                        
                        
                # Build environment config
                env_config = EnvironmentConfig(
                    name=env_name,
                    description=env_description,
                    metadata=env_metadata,
                    version=env_version,
                    enable_evolving=env_enable_evolving,
                    cls=env_cls,
                    config=env_config_dict,
                    instance=None,
                    code=env_code,
                    actions=env_actions,
                    rules=env_rules,  # from ENVIRONMENT.md body
                )
                
                env_configs[env_name] = env_config
                
                # Store in dict-based history (for quick lookup by version)
                if env_name not in self._environment_history_versions:
                    self._environment_history_versions[env_name] = {}
                self._environment_history_versions[env_name][env_version] = env_config
                
                # Register version to version manager
                await version_manager.register_version("environment", env_name, env_version)
                
                logger.info(f"| 📝 Registered environment: {env_name} ({env_cls.__name__})")

            except Exception as e:
                logger.error(f"| ❌ Failed to register environment class {env_cls.__name__}: {e}")
                raise
            
        import autogenesis.environment  # noqa: F401
        
        # Get all registered environment classes from ENVIRONMENT registry
        environment_classes = list(ENVIRONMENT._module_dict.values())
        
        logger.info(f"| 🔍 Discovering {len(environment_classes)} environments from ENVIRONMENT registry")
        
        # Register each environment class concurrently with a concurrency limit
        tasks = [
            register_environment_class(env_cls) for env_cls in environment_classes
        ]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)
        success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        
        logger.info(f"| ✅ Discovered and registered {success_count}/{len(environment_classes)} environments from ENVIRONMENT registry")
        
        return env_configs
    
    async def build(self, env_config: EnvironmentConfig) -> EnvironmentConfig:
        """Build an environment instance from config (internal helper, similar to tool's build).
        
        Args:
            env_config: Environment configuration
            
        Returns:
            EnvironmentConfig: Environment configuration with instance
        """
        if env_config.name in self._environment_configs:
            existing_config = self._environment_configs[env_config.name]
            if existing_config.instance is not None:
                return existing_config
        
        try:
            if env_config.cls is None:
                raise ValueError(f"Cannot create environment {env_config.name}: no class provided. Class should be loaded during initialization.")
            
            env_instance = env_config.cls(**env_config.config) if env_config.config else env_config.cls()
            
            # Initialize environment if it has an initialize method
            if hasattr(env_instance, "initialize"):
                await env_instance.initialize()
                
            env_config.instance = env_instance

            # Rules come from ENVIRONMENT.md (loaded at registration) — no code-generated fallback.
            if not env_config.rules:
                logger.warning(f"| ⚠️ Environment {env_config.name} has empty rules (missing ENVIRONMENT.md?)")

            # Store metadata
            self._environment_configs[env_config.name] = env_config
            
            logger.info(f"| ✅ Environment {env_config.name} created and stored")
            
            return env_config
        except Exception as e:
            logger.error(f"| ❌ Failed to create environment {env_config.name}: {e}")
            raise
    
    async def register(self, 
                       env_cls: Type[Environment], 
                       env_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None) -> EnvironmentConfig:
        """Register an environment class.
        
        This will:
        - Create an environment instance
        - Create an `EnvironmentConfig`
        - Store it as the current config and append to version history
        - Register the version in `version_manager` and FAISS index
        
        Args:
            env_cls: Environment class
            env_config_dict: Configuration dict for environment initialization.
                           If None, will try to get from global config or use empty dict.
            override: Whether to override existing registration
            version: Optional version string. If None, auto-generates from version_manager.
            
        Returns:
            EnvironmentConfig: Environment configuration
        """
        try:
            if env_config_dict is None:
                # Fallback to global config by class name
                env_config_key = inflection.underscore(env_cls.__name__)
                env_config_dict = getattr(config, env_config_key, {}) if hasattr(config, env_config_key) else {}
            
            # Ensure opensandbox-server is running if this environment needs it
            if env_config_dict and env_config_dict.get("use_sandbox", False):
                await self._ensure_sandbox_server({}, force=True)

            # Instantiate environment immediately (register is a runtime operation)
            try:
                env_instance = env_cls(**env_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create environment instance for {env_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate environment {env_cls.__name__} with provided config: {e}")
            
            env_name = env_instance.name
            env_description = env_instance.description
            env_metadata = getattr(env_instance, 'metadata', {})
            env_enable_evolving = getattr(env_instance, 'enable_evolving', False)
            
            if not env_name:
                raise ValueError("Environment.name cannot be empty.")
            
            if env_name in self._environment_configs and not override:
                raise ValueError(f"Environment '{env_name}' already registered. Use override=True to replace it.")
            
            # Get or generate version from version_manager
            if version is None:
                env_version = await version_manager.get_version("environment", env_name)
            else:
                env_version = version
            
            # Get environment code
            env_code = dynamic_manager.get_full_module_source(env_cls)
            
            # Build actions from environment class (same as _load_from_registry)
            actions = {}
            for attr_name in dir(env_cls):
                attr = getattr(env_cls, attr_name)
                if hasattr(attr, '_action_name'):
                    action_name = getattr(attr, '_action_name')
                    action_description = getattr(attr, '_action_description', '')
                    action_function = getattr(attr, '_action_function', None)
                    action_metadata = getattr(attr, '_action_metadata', {})
                    
                    action_version = await version_manager.get_version("action", action_name)
                    
                    action_code = dynamic_manager.get_source_code(attr)
                    if not action_code:
                        logger.warning(f"| ⚠️ Action {action_name} is dynamic but source code cannot be extracted")
                    
                    action_parameters = dynamic_manager.get_parameters(action_function)
                    action_function_calling = dynamic_manager.build_function_calling(action_name, action_description, action_parameters)
                    action_text = dynamic_manager.build_text_representation(action_name, action_description, action_parameters)
                    action_args_schema = dynamic_manager.build_args_schema(action_name, action_parameters)
                    
                    action_config = ActionConfig(
                        env_name=env_name,
                        name=action_name,
                        description=action_description,
                        function=action_function,
                        metadata=action_metadata,
                        version=action_version,
                        code=action_code,
                        function_calling=action_function_calling,
                        text=action_text,
                        args_schema=action_args_schema,
                    )
                    
                    actions[action_name] = action_config
            
            # Rules from the ENVIRONMENT.md beside the class (no code-generated get_rules)
            _env_md = self._load_environment_md(type(env_instance))
            env_rules = _env_md[1] if _env_md else ""
            
            # --- Build EnvironmentConfig ---
            env_config = EnvironmentConfig(
                name=env_name,
                description=env_description,
                rules=env_rules,
                version=env_version,
                enable_evolving=env_enable_evolving,
                actions=actions,
                cls=env_cls,
                config=env_config_dict or {},
                instance=env_instance,
                metadata=env_metadata,
                code=env_code
            )
            
            # --- Persist current config and history ---
            self._environment_configs[env_name] = env_config
            
            # Store in dict-based history (for quick lookup by version)
            if env_name not in self._environment_history_versions:
                self._environment_history_versions[env_name] = {}
            self._environment_history_versions[env_name][env_config.version] = env_config
            
            # Register version in version manager
            await version_manager.register_version("environment", env_name, env_config.version)
            
            # Persist to JSON
            
            logger.info(f"| 📝 Registered environment config: {env_name}: {env_config.version}")
            return env_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to register environment: {e}")
            raise
        
    async def get(self, env_name: str) -> Optional[Environment]:
        """Get environment instance by name
        
        Args:
            env_name: Environment name
            
        Returns:
            Environment: Environment instance or None if not found
        """
        env_config = self._environment_configs.get(env_name)
        if env_config:
            return env_config.instance
        return None
    
    async def get_info(self, env_name: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name
        
        Args:
            env_name: Environment name
            
        Returns:
            EnvironmentConfig: Environment configuration or None if not found
        """
        return self._environment_configs.get(env_name)
        
    async def get_state(self, env_name: str, ctx: EnvironmentContext = None, **kwargs) -> Optional[Dict[str, Any]]:
        """Get the state of an environment

        Args:
            env_name: Environment name
            ctx: Environment context
        Returns:
            Optional[Dict[str, Any]]: State of the environment or None if not found
        """

        if ctx is None:
            ctx = EnvironmentContext(name=env_name)
            
        env_args = {
            "ctx": ctx,
        }
        
        env_config = self._environment_configs.get(env_name)
        if not env_config or not env_config.instance:
            raise ValueError(f"Environment '{env_name}' not found")
        return await env_config.instance.get_state(**env_args)
        
    async def list(self) -> List[str]:
        """Get list of registered environments
        
        Args:
            include_disabled: Whether to include disabled environments (not used for environments, kept for compatibility)
            
        Returns:
            List[str]: List of registered environment names
        """
        return [name for name in self._environment_configs.keys()]
    
    
    async def update(self, 
                     env_cls: Type[Environment],
                     env_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None,
                     code: Optional[str] = None) -> EnvironmentConfig:
        """Update an existing environment with new configuration and create a new version
        
        Args:
            env_cls: New environment class with updated implementation
            env_config_dict: Configuration dict for environment initialization
                   If None, will try to get from global config
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string. If provided, uses this instead of extracting from env_cls.
                  This is useful when env_cls is dynamically created from code string.
            
        Returns:
            EnvironmentConfig: Updated environment configuration
        """
        try:
            if env_config_dict is None:
                # Fallback to global config by class name
                env_config_key = inflection.underscore(env_cls.__name__)
                env_config_dict = getattr(config, env_config_key, {}) if hasattr(config, env_config_key) else {}
            
            # Instantiate environment immediately (update is a runtime operation)
            try:
                env_instance = env_cls(**env_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create environment instance for {env_cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate environment {env_cls.__name__} with provided config: {e}")
            
            env_name = env_instance.name
            
            # Check if environment exists
            original_config = self._environment_configs.get(env_name)
            if original_config is None:
                raise ValueError(f"Environment {env_name} not found. Use register() to register a new environment.")
            
            env_description = env_instance.description
            env_metadata = getattr(env_instance, 'metadata', {})
            env_enable_evolving = env_config_dict.get("enable_evolving", getattr(env_instance, 'enable_evolving', False)) if env_config_dict and "enable_evolving" in env_config_dict else getattr(env_instance, 'enable_evolving', False)
            
            # Determine new version from version_manager
            if new_version is None:
                # Get current version from version_manager and generate next patch version
                new_version = await version_manager.generate_next_version("environment", env_name, "patch")
            
            # Get environment code - use provided code if available (for dynamically created classes)
            if code is not None:
                env_code = code
            else:
                env_code = dynamic_manager.get_full_module_source(env_cls)
            
            # Build actions from environment class (same as register)
            actions = {}
            for attr_name in dir(env_cls):
                attr = getattr(env_cls, attr_name)
                if hasattr(attr, '_action_name'):
                    action_name = getattr(attr, '_action_name')
                    action_description = getattr(attr, '_action_description', '')
                    action_function = getattr(attr, '_action_function', None)
                    action_metadata = getattr(attr, '_action_metadata', {})
                    
                    action_version = await version_manager.get_version("action", action_name)
                    
                    action_code = dynamic_manager.get_source_code(attr)
                    if not action_code:
                        logger.warning(f"| ⚠️ Action {action_name} is dynamic but source code cannot be extracted")
                    
                    action_parameters = dynamic_manager.get_parameters(action_function)
                    action_function_calling = dynamic_manager.build_function_calling(action_name, action_description, action_parameters)
                    action_text = dynamic_manager.build_text_representation(action_name, action_description, action_parameters)
                    action_args_schema = dynamic_manager.build_args_schema(action_name, action_parameters)
                    
                    action_config = ActionConfig(
                        env_name=env_name,
                        name=action_name,
                        description=action_description,
                        function=action_function,
                        metadata=action_metadata,
                        version=action_version,
                        code=action_code,
                        function_calling=action_function_calling,
                        text=action_text,
                        args_schema=action_args_schema,
                    )
                    
                    actions[action_name] = action_config
            
            # Rules from the ENVIRONMENT.md beside the class (no code-generated get_rules)
            _env_md = self._load_environment_md(type(env_instance))
            env_rules = _env_md[1] if _env_md else ""
            
            # --- Build EnvironmentConfig ---
            updated_config = EnvironmentConfig(
                name=env_name,  # Keep same name
                description=env_description,
                rules=env_rules,
                version=new_version,
                enable_evolving=env_enable_evolving,
                actions=actions,
                cls=env_cls,
                config=env_config_dict or {},
                instance=env_instance,
                metadata=env_metadata,
                code=env_code
            )
            
            # Update the environment config (replaces current version)
            self._environment_configs[env_name] = updated_config
            
            # Store in version history
            if env_name not in self._environment_history_versions:
                self._environment_history_versions[env_name] = {}
            self._environment_history_versions[env_name][updated_config.version] = updated_config
            
            # Register new version record to version manager
            await version_manager.register_version(
                "environment", 
                env_name, 
                new_version,
                description=description or f"Updated from {original_config.version}"
            )
            
            # Persist to JSON
            
            logger.info(f"| 🔄 Updated environment {env_name} from v{original_config.version} to v{new_version}")
            return updated_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to update environment: {e}")
            raise
    
    async def copy(self, 
                  env_name: str,
                  new_name: Optional[str] = None, 
                  new_version: Optional[str] = None, 
                  new_config: Optional[Dict[str, Any]] = None) -> EnvironmentConfig:
        """Copy an existing environment configuration
        
        Args:
            env_name: Name of the environment to copy
            new_name: New name for the copied environment. If None, uses original name.
            new_version: New version for the copied environment. If None, increments version.
            new_config: New configuration dict for the copied environment. If None, uses original config.
            
        Returns:
            EnvironmentConfig: New environment configuration
        """
        try:
            original_config = self._environment_configs.get(env_name)
            if original_config is None:
                raise ValueError(f"Environment {env_name} not found")
            
            if original_config.cls is None:
                raise ValueError(f"Cannot copy environment {env_name}: no class provided")
            
            # Determine new name
            if new_name is None:
                new_name = env_name
            
            # Prepare config dict (merge original config with new config)
            env_config_dict = original_config.config.copy() if original_config.config else {}
            if new_config:
                # Merge new config into original config
                env_config_dict.update(new_config)
            
            # Instantiate environment instance (copy is a runtime operation)
            try:
                env_instance = original_config.cls(**env_config_dict)
            except Exception as e:
                logger.error(f"| ❌ Failed to create environment instance for {original_config.cls.__name__}: {e}")
                raise ValueError(f"Failed to instantiate environment {original_config.cls.__name__} with provided config: {e}")
            
            # Apply name override if provided (after instantiation)
            if new_name != env_name:
                env_instance.name = new_name
            
            env_description = env_instance.description
            env_metadata = getattr(env_instance, 'metadata', {})
            env_enable_evolving = env_config_dict.get("enable_evolving", getattr(env_instance, 'enable_evolving', False)) if env_config_dict and "enable_evolving" in env_config_dict else getattr(env_instance, 'enable_evolving', False)
            
            # Determine new version from version_manager
            if new_version is None:
                if new_name == env_name:
                    # If copying with same name, get next version from version_manager
                    new_version = await version_manager.generate_next_version("environment", new_name, "patch")
                else:
                    # If copying with different name, get or generate version for new name
                    new_version = await version_manager.get_version("environment", new_name)
            
            # Get environment code
            env_code = dynamic_manager.get_full_module_source(original_config.cls)
            
            # Build actions from environment class (same as register)
            actions = {}
            for attr_name in dir(original_config.cls):
                attr = getattr(original_config.cls, attr_name)
                if hasattr(attr, '_action_name'):
                    action_name = getattr(attr, '_action_name')
                    action_description = getattr(attr, '_action_description', '')
                    action_function = getattr(attr, '_action_function', None)
                    action_metadata = getattr(attr, '_action_metadata', {})
                    
                    action_version = await version_manager.get_version("action", action_name)
                    
                    action_code = dynamic_manager.get_source_code(attr)
                    if not action_code:
                        logger.warning(f"| ⚠️ Action {action_name} is dynamic but source code cannot be extracted")
                    
                    action_parameters = dynamic_manager.get_parameters(action_function)
                    action_function_calling = dynamic_manager.build_function_calling(action_name, action_description, action_parameters)
                    action_text = dynamic_manager.build_text_representation(action_name, action_description, action_parameters)
                    action_args_schema = dynamic_manager.build_args_schema(action_name, action_parameters)
                    
                    action_config = ActionConfig(
                        env_name=new_name,
                        name=action_name,
                        description=action_description,
                        function=action_function,
                        metadata=action_metadata,
                        version=action_version,
                        code=action_code,
                        function_calling=action_function_calling,
                        text=action_text,
                        args_schema=action_args_schema,
                    )
                    
                    actions[action_name] = action_config
            
            # Rules from the ENVIRONMENT.md beside the class (no code-generated get_rules)
            _env_md = self._load_environment_md(type(env_instance))
            env_rules = _env_md[1] if _env_md else ""
            
            # --- Build EnvironmentConfig ---
            copied_config = EnvironmentConfig(
                name=new_name,
                description=env_description,
                rules=env_rules,
                version=new_version,
                enable_evolving=env_enable_evolving,
                actions=actions,
                cls=original_config.cls,
                config=env_config_dict,
                instance=env_instance,
                metadata=env_metadata,
                code=env_code
            )
            
            # Register new environment
            self._environment_configs[new_name] = copied_config
            
            # Store in version history
            if new_name not in self._environment_history_versions:
                self._environment_history_versions[new_name] = {}
            self._environment_history_versions[new_name][new_version] = copied_config
            
            # Register version record to version manager
            await version_manager.register_version(
                "environment", 
                new_name, 
                new_version,
                description=f"Copied from {env_name}@{original_config.version}"
            )
            
            # Persist to JSON
            
            logger.info(f"| 📋 Copied environment {env_name}@{original_config.version} to {new_name}@{new_version}")
            return copied_config
        
        except Exception as e:
            logger.error(f"| ❌ Failed to copy environment: {e}")
            raise
    
    async def unregister(self, env_name: str) -> bool:
        """Unregister an environment
        
        Args:
            env_name: Name of the environment to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        if env_name not in self._environment_configs:
            logger.warning(f"| ⚠️ Environment {env_name} not found")
            return False
        
        env_config = self._environment_configs[env_name]
        
        # Remove from configs
        del self._environment_configs[env_name]

        # Persist to JSON after unregister
        # Save contract to file
        
        logger.info(f"| 🗑️ Unregistered environment {env_name}@{env_config.version}")
        return True
    
    async def restore(self, env_name: str, version: str, auto_initialize: bool = True) -> Optional[EnvironmentConfig]:
        """Restore a specific version of an environment from history
        
        Args:
            env_name: Name of the environment
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored environment
            
        Returns:
            EnvironmentConfig of the restored version, or None if not found
        """
        # Look up version from dict-based history (O(1) lookup)
        version_config = None
        if env_name in self._environment_history_versions:
            version_config = self._environment_history_versions[env_name].get(version)
        
        if version_config is None:
            logger.warning(f"| ⚠️ Version {version} not found for environment {env_name}")
            return None
        
        # Create a copy to avoid modifying the history
        restored_config = EnvironmentConfig(**version_config.model_dump())
        
        # Set as current active config
        self._environment_configs[env_name] = restored_config
        
        # Update version manager current version
        version_history = await version_manager.get_version_history("environment", env_name)
        if version_history:
            # Check if version exists in version history, if not register it
            if version not in version_history.versions:
                await version_manager.register_version("environment", env_name, version)
            version_history.current_version = version
        else:
            # If version history doesn't exist, register the version first
            await version_manager.register_version("environment", env_name, version)
        
        # Initialize if requested
        if auto_initialize and restored_config.cls is not None:
            await self.build(restored_config)
        
        # Persist to JSON (current_version changes)
        
        logger.info(f"| 🔄 Restored environment {env_name} to version {version}")
        return restored_config
    
    async def _ensure_sandbox_server(self, env_configs: Dict[str, EnvironmentConfig], force: bool = False) -> None:
        """Start opensandbox-server if any registered environment requires it."""
        needs_sandbox = force or any(
            cfg.config and cfg.config.get("use_sandbox", False)
            for cfg in env_configs.values()
        )
        if not needs_sandbox:
            return
        logger.info("| 🔍 Sandbox-based environment detected — ensuring opensandbox-server is running")
        await self._sandbox_server.ensure_running()

    async def cleanup(self):
        """Cleanup all active environments."""
        try:
            # Cleanup all instances
            for env_name, env_config in self._environment_configs.items():
                if env_config.instance and hasattr(env_config.instance, "cleanup"):
                    try:
                        await env_config.instance.cleanup()
                    except Exception as e:
                        logger.warning(f"| ⚠️ Error cleaning up environment {env_name} instance: {e}")
            
            # Clear all environment configs and version history
            self._environment_configs.clear()
            self._environment_history_versions.clear()

            # Shut down opensandbox-server if we started it
            await self._sandbox_server.shutdown()

            logger.info("| 🧹 Environment context manager cleaned up")
            
        except Exception as e:
            logger.error(f"| ❌ Error during environment context manager cleanup: {e}")
            
    async def __call__(self, 
                       name: str, 
                       action: str, 
                       input: Dict[str, Any], 
                       ctx: EnvironmentContext = None,
                       **kwargs) -> Any:
        """Call an environment action
        
        Args:
            name: Name of the environment
            action: Name of the action
            input: Input for the action
            
        Returns:
            Action result
        """
        if name in self._environment_configs:
            env_config = self._environment_configs[name]
            
            version = env_config.version
            env_instance = env_config.instance
            logger.info(f"| ✅ Using environment {name}@{version}")
            
            action_config = env_config.actions.get(action)
            if action_config is None:
                raise ValueError(f"Action {action} not found in environment {name}")
            action_function = action_config.function
            
            # Environment args
            env_args = {
                "ctx": ctx,
            }
            
            # Check if action_function is a bound method (already has self bound)
            # Bound methods have __self__ attribute, unbound methods don't
            if hasattr(action_function, '__self__'):
                # Bound method: call directly without passing instance
                return await action_function(**input, **env_args)
            else:
                # Unbound method: pass instance as first argument
                return await action_function(env_instance, **input, **env_args)
        else:
            raise ValueError(f"Environment {name} not found")
