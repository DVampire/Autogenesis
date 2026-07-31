"""ECP Server

Server implementation for the Environment Context Protocol with lazy loading support.
"""
from typing import Any, Dict, List, Optional, Tuple, Type, Union, Callable

import os
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.environment.context import EnvironmentContextManager
from autogenesis.environment.types import Environment, EnvironmentConfig, EnvironmentContext
from autogenesis.utils import assemble_workspace_path
from autogenesis.capability import CapabilitySchema, SchemaSource

class EnvironmentManagerServer(BaseModel):
    """ECP Server for managing environment registration and execution with lazy loading."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    base_dir: str = Field(default=None, description="The base directory to use for the environments")
    
    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the ECP Server."""
        super().__init__(**kwargs)
        self._registered_configs: Dict[str, EnvironmentConfig] = {}  # env_name -> EnvironmentConfig
        # (session_id, env_name) -> last announced live-view URL, to dedupe announcements.
        self._announced_views: Dict[tuple, str] = {}

        
    async def initialize(self, env_names: Optional[List[str]] = None):
        """Initialize environments by names using environment context manager with concurrent support.
        
        Args:
            env_names: List of environment names to initialize. If None, initialize all registered environments.
        """

        base_root = config.log_root if hasattr(config, "log_root") and config.get("log_root") else config.workspace_root
        self.base_dir = assemble_workspace_path(os.path.join(base_root, "environment"))
        logger.info(f"| 📁 ECP Server base directory: {self.base_dir}")

        # Initialize environment context manager
        self.environment_context_manager = EnvironmentContextManager(
            base_dir=self.base_dir,
        )
        await self.environment_context_manager.initialize(env_names=env_names)
        
        logger.info("| ✅ Environments initialization completed")
        
    def action(self, 
               name: str = None, 
               description: str = "",
               metadata: Optional[Dict[str, Any]] = None):
        """Decorator to register an action (tool) for an environment
        
        Actions will be registered to the environment instance's actions dictionary during instantiation.
        
        Args:
            name: Action name (defaults to function name)
            description: Action description
            metadata: Action metadata
        """
        def decorator(func: Callable):
            action_name = name or func.__name__
            
            func._action_name = action_name
            func._action_description = description
            func._action_function = func
            func._action_metadata = metadata if metadata is not None else {}
            
            return func
        return decorator
    
    async def register(self, 
                       env_cls: Type[Environment],
                       env_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None) -> EnvironmentConfig:
        """Register an environment class asynchronously.
        
        Args:
            env_cls: Environment class to register
            env_config_dict: Configuration dict for environment initialization
            override: Whether to override existing registration
            version: Optional version string
            
        Returns:
            EnvironmentConfig: Environment configuration
        """
        if not hasattr(self, "environment_context_manager"):
            await self.initialize(env_names=[])
        env_config = await self.environment_context_manager.register(
            env_cls,
            env_config_dict=env_config_dict, 
            override=override,
            version=version
        )
        self._registered_configs[env_config.name] = env_config
        return env_config
    
    async def list(self) -> List[str]:
        """List all registered environments
        
        Returns:
            List[str]: List of environment names
        """
        if not hasattr(self, "environment_context_manager"):
            return []
        return await self.environment_context_manager.list()

    async def function_callings(
        self, allowlist: Optional[List[str]] = None
    ) -> List[Tuple[Dict[str, Any], Tuple[str, str, str]]]:
        """Expose selected environment actions as native tool-calling schemas."""
        names = allowlist if allowlist is not None else await self.list()
        out: List[Tuple[Dict[str, Any], Tuple[str, str, str]]] = []
        for env_name in names:
            info = await self.get_info(env_name)
            if info is None:
                continue
            for action_name in (getattr(info, "actions", {}) or {}):
                fc = await self.get_schema(env_name, action=action_name, format="json")
                if fc:
                    out.append((fc, ("environment", env_name, action_name)))
        return out

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Return one Environment action contract from declared/inferred metadata."""
        info = await self.get_info(name)
        actions = (getattr(info, "actions", {}) or {}) if info is not None else {}
        item = actions.get(action) if action else None
        if item is None:
            return None
        function_calling = getattr(item, "function_calling", None) or {}
        function = function_calling.get("function", {}) if isinstance(function_calling, dict) else {}
        parameters = function.get("parameters") if isinstance(function, dict) else None
        source = SchemaSource.DECLARED
        if not isinstance(parameters, dict):
            args_schema = getattr(item, "args_schema", None)
            if args_schema is not None and hasattr(args_schema, "model_json_schema"):
                parameters = args_schema.model_json_schema()
                source = SchemaSource.INFERRED
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "additionalProperties": True}
            source = SchemaSource.LEGACY_FALLBACK
        return CapabilitySchema(
            name=f"{name}__{action}",
            description=getattr(item, "description", "") or f"{name}: {action}",
            parameters=parameters,
            strict=parameters.get("additionalProperties") is False,
            source=source,
        ).render(format)
    
    
    async def get(self, env_name: str) -> Optional[Environment]:
        """Get environment instance by name
        
        Args:
            env_name: Environment name
            
        Returns:
            Environment: Environment instance or None if not found
        """
        return await self.environment_context_manager.get(env_name)
    
    async def get_info(self, env_name: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name
        
        Args:
            env_name: Environment name
            
        Returns:
            EnvironmentConfig: Environment configuration or None if not found
        """
        return await self.environment_context_manager.get_info(env_name)
    
    async def get_state(self, env_name: str, ctx: EnvironmentContext = None, **kwargs) -> Optional[Dict[str, Any]]:
        """Get the state of an environment
        
        Args:
            env_name: Environment name
            ctx: Environment context
            
        Returns:
            Optional[Dict[str, Any]]: State of the environment or None if not found
        """
        return await self.environment_context_manager.get_state(env_name, ctx, **kwargs)
    
    async def cleanup(self):
        """Cleanup all environments"""
        await self.environment_context_manager.cleanup()
        self._registered_configs.clear()
    
    async def update(self, 
                     env_cls: Type[Environment],
                     env_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None) -> EnvironmentConfig:
        """Update an existing environment with new configuration and create a new version
        
        Args:
            env_cls: New environment class with updated implementation
            env_config_dict: Configuration dict for environment initialization
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            
        Returns:
            EnvironmentConfig: Updated environment configuration
        """
        env_config = await self.environment_context_manager.update(
            env_cls, env_config_dict=env_config_dict, new_version=new_version, description=description
        )
        self._registered_configs[env_config.name] = env_config
        return env_config
    
    async def copy(self, 
                  env_name: str,
                  new_name: Optional[str] = None, 
                  new_version: Optional[str] = None, 
                  new_config: Optional[Dict[str, Any]] = None) -> EnvironmentConfig:
        """Copy an existing environment
        
        Args:
            env_name: Name of the environment to copy
            new_name: New name for the copied environment. If None, uses original name.
            new_version: New version for the copied environment. If None, increments version.
            new_config: New configuration dict for the copied environment. If None, uses original config.
            
        Returns:
            EnvironmentConfig: New environment configuration
        """
        env_config = await self.environment_context_manager.copy(
            env_name, new_name, new_version, new_config
        )
        self._registered_configs[env_config.name] = env_config
        return env_config
    
    async def unregister(self, env_name: str) -> bool:
        """Unregister an environment
        
        Args:
            env_name: Name of the environment to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        success = await self.environment_context_manager.unregister(env_name)
        if success and env_name in self._registered_configs:
            del self._registered_configs[env_name]
        return success
    
    async def restore(self, env_name: str, version: str, auto_initialize: bool = True) -> Optional[EnvironmentConfig]:
        """Restore a specific version of an environment from history
        
        Args:
            env_name: Name of the environment
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored environment
            
        Returns:
            EnvironmentConfig of the restored version, or None if not found
        """
        env_config = await self.environment_context_manager.restore(env_name, version, auto_initialize)
        if env_config:
            self._registered_configs[env_config.name] = env_config
        return env_config
    
    async def __call__(self,
                       name: str, 
                       action: str, 
                       input: Dict[str, Any], 
                       ctx: EnvironmentContext = None,
                       **kwargs) -> Any:
        """Call an environment action

        Args:
            name (str): Name of the environment
            action (str): Name of the action
            input (Dict[str, Any]): Input for the action
            ctx (EnvironmentContext): Environment context
            
        Returns:
            Any: Action result
        """
        if ctx is None:
            ctx = EnvironmentContext(name=name, action=action, input=input)
        elif not isinstance(ctx, EnvironmentContext):
            # Accept a caller's context (e.g. AgentContext) — carry over its id/workspace_root
            ctx = EnvironmentContext.from_context(ctx)
        result = await self.environment_context_manager(name, action, input, ctx, **kwargs)
        # After every action, let the environment advertise a live view (e.g. the
        # headful browser's noVNC socket) so the frontend can watch it. Generic:
        # any environment that implements live_view() streams with no manager change.
        await self._announce_live_view(name, ctx)
        return result

    async def _announce_live_view(self, name: str, ctx: EnvironmentContext) -> None:
        """Announce this environment's live-view endpoint on change (idempotent)."""
        try:
            env = await self.get(name)
            if env is None:
                return
            view = await env.live_view(ctx)
            if view is None:
                return
            view.session_id = view.session_id or getattr(ctx, "id", "") or ""
            view.env_name = view.env_name or name
            key = (view.session_id, name)
            if self._announced_views.get(key) == view.url:
                return  # same endpoint already announced — don't spam the bus
            self._announced_views[key] = view.url
            from autogenesis.environment.stream import environment_stream
            await environment_stream.emit(view)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ live_view announce failed for '{name}': {exc}")


# Global EnvironmentManager server instance
environment_manager = EnvironmentManagerServer()
