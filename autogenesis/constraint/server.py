"""Constraint Manager Server

Server implementation for constraint management with lazy loading support.
"""
from typing import Any, Dict, List, Optional, Type, Union
import os
from pydantic import BaseModel, ConfigDict, Field


from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.constraint.context import ConstraintContextManager
from autogenesis.constraint.types import Constraint, ConstraintConfig, ConstraintContext
from autogenesis.response.types import Response
from autogenesis.utils import assemble_workspace_path


class ConstraintManagerServer(BaseModel):
    """constraint manager Server for managing constraint registration and execution with lazy loading."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    base_dir: str = Field(default=None, description="The base directory to use for the constraints")

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the constraint manager Server."""
        super().__init__(**kwargs)
        self._registered_configs: Dict[str, ConstraintConfig] = {}  # constraint_name -> ConstraintConfig
        # Context manager is created lazily (config may not be loaded at import time).
        # initialize() reconfigures it with proper base_dir .
        self.constraint_context_manager: Optional[ConstraintContextManager] = None

    def _ensure_context_manager(self) -> ConstraintContextManager:
        """Lazily create the context manager so register / __call__ work before initialize() is called."""
        if self.constraint_context_manager is None:
            self.constraint_context_manager = ConstraintContextManager()
        return self.constraint_context_manager

    async def initialize(self, constraint_names: Optional[List[str]] = None):
        """Initialize constraints by names using constraint context manager with concurrent support.

        Args:
            constraint_names: List of constraint names to initialize. If None, initialize all registered constraints.
        """

        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "constraint"))
        logger.info(f"| 📁 constraint manager Server base directory: {self.base_dir}")

        # Initialize constraint context manager
        self.constraint_context_manager = ConstraintContextManager(
            base_dir=self.base_dir,
            model_name="openrouter/gemini-3-flash-preview",
        )
        await self._ensure_context_manager().initialize(constraint_names=constraint_names)

        logger.info("| ✅ Constraints initialization completed")

    async def register(self,
                       constraint: Union[Constraint, Type[Constraint]],
                       config: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None,
                       code: Optional[str] = None) -> ConstraintConfig:
        """Register a constraint class or instance asynchronously.

        Args:
            constraint: Constraint class or instance to register
            config: Configuration dict for constraint initialization (required when constraint is a class)
            override: Whether to override existing registration
            version: Optional version string
            code: Optional explicit source code for the constraint class

        Returns:
            ConstraintConfig: Constraint configuration
        """
        constraint_config = await self._ensure_context_manager().register(
            constraint,
            constraint_config_dict=config,
            override=override,
            version=version,
            code=code
        )
        self._registered_configs[constraint_config.name] = constraint_config
        return constraint_config

    async def list(self) -> List[str]:
        """List all registered constraints

        Returns:
            List[str]: List of constraint names
        """
        return await self._ensure_context_manager().list()

    async def get(self, constraint_name: str) -> Optional[Constraint]:
        """Get constraint instance by name

        Args:
            constraint_name: Constraint name

        Returns:
            Constraint: Constraint instance or None if not found
        """
        constraint = await self._ensure_context_manager().get(constraint_name)
        return constraint

    async def get_info(self, constraint_name: str) -> Optional[ConstraintConfig]:
        """Get constraint configuration by name

        Args:
            constraint_name: Constraint name

        Returns:
            ConstraintConfig: Constraint configuration or None if not found
        """
        return await self._ensure_context_manager().get_info(constraint_name)

    async def cleanup(self):
        """Cleanup all constraints"""
        await self._ensure_context_manager().cleanup()
        self._registered_configs.clear()

    async def update(self,
                     constraint_name: str, constraint: Union[Constraint, Type[Constraint]],
                     config: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None,
                     description: Optional[str] = None,
                     code: Optional[str] = None) -> ConstraintConfig:
        """Update an existing constraint with new configuration and create a new version

        Args:
            constraint_name: Name of the constraint to update
            constraint: New constraint class or instance with updated implementation
            config: Configuration dict for constraint initialization (required when constraint is a class)
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            code: Optional source code string (used when constraint class is dynamically loaded)

        Returns:
            ConstraintConfig: Updated constraint configuration
        """
        constraint_config = await self._ensure_context_manager().update(
            constraint, constraint_config_dict=config, new_version=new_version, description=description, code=code
        )
        self._registered_configs[constraint_config.name] = constraint_config
        return constraint_config

    async def copy(self, constraint_name: str, new_name: Optional[str] = None,
                  new_version: Optional[str] = None, **override_config) -> ConstraintConfig:
        """Copy an existing constraint

        Args:
            constraint_name: Name of the constraint to copy
            new_name: New name for the copied constraint. If None, uses original name.
            new_version: New version for the copied constraint. If None, increments version.
            **override_config: Configuration overrides

        Returns:
            ConstraintConfig: New constraint configuration
        """
        constraint_config = await self._ensure_context_manager().copy(
            constraint_name, new_name, new_version, override_config or None
        )
        self._registered_configs[constraint_config.name] = constraint_config
        return constraint_config

    async def unregister(self, constraint_name: str) -> bool:
        """Unregister a constraint

        Args:
            constraint_name: Name of the constraint to unregister

        Returns:
            True if unregistered successfully, False otherwise
        """
        success = await self._ensure_context_manager().unregister(constraint_name)
        if success and constraint_name in self._registered_configs:
            del self._registered_configs[constraint_name]
        return success

    async def restore(self, constraint_name: str, version: str, auto_initialize: bool = True) -> Optional[ConstraintConfig]:
        """Restore a specific version of a constraint from history

        Args:
            constraint_name: Name of the constraint
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored constraint

        Returns:
            ConstraintConfig of the restored version, or None if not found
        """
        constraint_config = await self._ensure_context_manager().restore(constraint_name, version, auto_initialize)
        if constraint_config:
            self._registered_configs[constraint_config.name] = constraint_config
        return constraint_config

    async def __call__(self,
                       name: str,
                       input: Dict[str, Any],
                       ctx: ConstraintContext = None,
                       **kwargs
                       ) -> Response:
        """Call a constraint by name with optional timeout and context

        Args:
            name: Constraint name
            input: Input for the constraint
            ctx: Constraint context

        Returns:
            Response: Constraint result
        """
        # Ensure ctx is always a ConstraintContext instance
        ctx = ConstraintContext.from_context(ctx) if ctx else ConstraintContext(name=name, input=input)
        return await self._ensure_context_manager()(name, input, ctx=ctx, **kwargs)


# Global constraint manager instance
constraint_manager = ConstraintManagerServer()
