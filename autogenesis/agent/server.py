"""Agent Server

Server implementation for the Agent Context Protocol with lazy loading support.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.agent.types import AgentConfig, Agent, AgentContext
from autogenesis.agent.context import AgentContextManager
from autogenesis.utils import assemble_workspace_path
from autogenesis.capability import CapabilitySchema, SchemaSource

class AgentManagerServer(BaseModel):
    """Agent Manager Server for managing agent registration and execution with lazy loading."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    base_dir: str = Field(default=None, description="The base directory to use for the agents")
    
    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        """Initialize the Agent Server."""
        super().__init__(**kwargs)
        self._registered_configs: Dict[str, AgentConfig] = {}  # agent_name -> AgentConfig
        # Context manager is created lazily (config may not be loaded at import time).
        # initialize() reconfigures it with proper base_dir .
        self.agent_context_manager: Optional[AgentContextManager] = None

        
    def _ensure_context_manager(self) -> AgentContextManager:
        """Lazily create the context manager so methods work before initialize() is called."""
        if self.agent_context_manager is None:
            self.agent_context_manager = AgentContextManager()
        return self.agent_context_manager

    async def initialize(self, agent_names: Optional[List[str]] = None):
        """Initialize agents by names using agent context manager with concurrent support.
        
        Args:
            agent_names: List of agent names to initialize. If None, initialize all registered agents.
        """
        
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "agent"))
        logger.info(f"| 📁 agent manager Server base directory: {self.base_dir}")
        
        # Initialize agent context manager
        self.agent_context_manager = AgentContextManager(
            base_dir=self.base_dir,
            model_name="openrouter/gemini-3-flash-preview",
        )
        await self._ensure_context_manager().initialize(agent_names=agent_names)
        
        # Sync registered_configs from context manager after initialization
        agent_list = await self._ensure_context_manager().list()
        for agent_name in agent_list:
            agent_config = await self._ensure_context_manager().get_info(agent_name)
            if agent_config and agent_name not in self._registered_configs:
                self._registered_configs[agent_name] = agent_config
        
        logger.info("| ✅ Agents initialization completed")

    async def register(self, 
                       agent_cls: Type[Agent],
                       agent_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None) -> AgentConfig:
        """Register an agent class asynchronously.
        
        Args:
            agent_cls: Agent class to register
            agent_config_dict: Configuration dict for agent initialization
            override: Whether to override existing registration
            version: Optional version string
            
        Returns:
            AgentConfig: Agent configuration
        """
        agent_config = await self._ensure_context_manager().register(
            agent_cls, 
            agent_config_dict=agent_config_dict, 
            override=override,
            version=version
        )
        self._registered_configs[agent_config.name] = agent_config
        return agent_config
    
    async def get_info(self, agent_name: str) -> Optional[AgentConfig]:
        """Get agent configuration by name
        
        Args:
            agent_name: Agent name
            
        Returns:
            AgentConfig: Agent configuration or None if not found
        """
        return await self._ensure_context_manager().get_info(agent_name)
    
    async def list(self) -> List[str]:
        """List all registered agents

        Returns:
            List[str]: List of agent names
        """
        return await self._ensure_context_manager().list()

    async def function_callings(
        self, allowlist: Optional[List[str]] = None, *, exclude: Optional[str] = None
    ) -> List[Tuple[Dict[str, Any], Tuple[Any, ...]]]:
        """Native tool-calling schemas for dispatchable sub-agents, each paired with its
        route. Used by orchestrators (MetaAgent) that project agents as callables. The
        function name is the agent's own registered name (already ``*_agent``, no
        prefixing); the schema is the uniform sub-agent brief.

        ``exclude`` drops one name (the caller, so an orchestrator never dispatches
        itself). Returns ``[(function_calling, ("agent", name)), ...]``.
        """
        names = allowlist if allowlist is not None else await self.list()
        out: List[Tuple[Dict[str, Any], Tuple[Any, ...]]] = []
        for n in names:
            if n == exclude:
                continue
            fc = await self.get_schema(n, format="json")
            if fc:
                out.append((fc, ("agent", n)))
        return out

    @staticmethod
    def _dispatch_parameters() -> Dict[str, Any]:
        """JSON schema for the uniform sub-agent delegation contract.

        Defines the parameters an orchestrator passes when dispatching any sub-agent as
        a callable (``task`` plus optional files, evolution target, and per-capability
        allowlists), so every agent is projected with the same strict function schema.
        """
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Precise, self-contained instruction — the sub-agent receives only this."},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Existing file paths to pass as context; omit if none."},
                "target_name": {"type": "string", "description": "ONLY for evaluator/optimizer/generator: the capability being evaluated/improved/created."},
                "tool_allowlist": {"type": "array", "items": {"type": "string"}, "description": "Evolution probe only: restrict the sub-agent to exactly these tools (empty list = baseline with none)."},
                "skill_allowlist": {"type": "array", "items": {"type": "string"}, "description": "Evolution probe only: restrict the sub-agent to exactly these skills."},
                "connector_allowlist": {"type": "array", "items": {"type": "string"}, "description": "Evolution probe only: restrict the sub-agent to exactly these connectors."},
                "environment_allowlist": {"type": "array", "items": {"type": "string"}, "description": "Restrict the sub-agent to these Environment capabilities."},
                "workflow_allowlist": {"type": "array", "items": {"type": "string"}, "description": "Evolution probe only: restrict the sub-agent to exactly these workflows."},
            },
            "required": ["task"],
            "additionalProperties": False,
        }

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Return the strict, uniform sub-agent delegation contract."""
        info = await self.get_info(name)
        if info is None:
            return None
        return CapabilitySchema(
            name=name, description=getattr(info, "description", "") or name,
            parameters=self._dispatch_parameters(), strict=True,
            source=SchemaSource.DECLARED,
        ).render(format)
    
    
    async def get(self, agent_name: str) -> Optional[Agent]:
        """Get agent instance by name
        
        Args:
            agent_name: Agent name
            
        Returns:
            Agent: Agent instance or None if not found
        """
        agent = await self._ensure_context_manager().get(agent_name)
        return agent
    
    async def cleanup(self):
        """Cleanup all agents"""
        await self._ensure_context_manager().cleanup()
        self._registered_configs.clear()
    
    async def update(self, 
                     agent_cls: Type[Agent],
                     agent_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None) -> AgentConfig:
        """Update an existing agent with new configuration and create a new version
        
        Args:
            agent_cls: New agent class with updated implementation
            agent_config_dict: Configuration dict for agent initialization
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            
        Returns:
            AgentConfig: Updated agent configuration
        """
        agent_config = await self._ensure_context_manager().update(
            agent_cls, agent_config_dict=agent_config_dict, new_version=new_version, description=description
        )
        self._registered_configs[agent_config.name] = agent_config
        return agent_config
    
    async def copy(self, 
                  agent_name: str,
                  new_name: Optional[str] = None, 
                  new_version: Optional[str] = None, 
                  new_config: Optional[Dict[str, Any]] = None) -> AgentConfig:
        """Copy an existing agent
        
        Args:
            agent_name: Name of the agent to copy
            new_name: New name for the copied agent. If None, uses original name.
            new_version: New version for the copied agent. If None, increments version.
            new_config: New configuration dict for the copied agent. If None, uses original config.
            
        Returns:
            AgentConfig: New agent configuration
        """
        agent_config = await self._ensure_context_manager().copy(
            agent_name, new_name, new_version, new_config
        )
        self._registered_configs[agent_config.name] = agent_config
        return agent_config
    
    async def unregister(self, agent_name: str) -> bool:
        """Unregister an agent
        
        Args:
            agent_name: Name of the agent to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        success = await self._ensure_context_manager().unregister(agent_name)
        if success and agent_name in self._registered_configs:
            del self._registered_configs[agent_name]
        return success
    
    async def restore(self, agent_name: str, version: str, auto_initialize: bool = True) -> Optional[AgentConfig]:
        """Restore a specific version of an agent from history
        
        Args:
            agent_name: Name of the agent
            version: Version string to restore
            auto_initialize: Whether to automatically initialize the restored agent
            
        Returns:
            AgentConfig of the restored version, or None if not found
        """
        agent_config = await self._ensure_context_manager().restore(agent_name, version, auto_initialize)
        if agent_config:
            self._registered_configs[agent_config.name] = agent_config
        return agent_config
    
    async def __call__(self, 
                       name: str, 
                       input: Dict[str, Any], 
                       ctx: AgentContext = None,
                       **kwargs) -> Any:
        """Call an agent method using context manager.
        
        Args:
            name: Name of the agent
            input: Input for the agent
            ctx: Agent context
            **kwargs: Keyword arguments for the agent
            
        Returns:
            Agent result
        """
        
        # Ensure ctx is always an AgentContext instance
        ctx = AgentContext.from_context(ctx) if ctx else AgentContext(name=name, input=input)
        # Direct Python entry points historically supplied only an id. Attach those
        # contexts to a session sandbox just as Gateway and CLI invocations are.
        from autogenesis.session.project import ensure_session_sandbox, stage_input_files
        # No explicit root: the layout puts this exactly where the gateway puts
        # a session, so a locally-started task and a browser-started one share
        # output/<owner>/sessions/<id> rather than diverging.
        ensure_session_sandbox(
            ctx,
            shared_extension_root=config.extension_root,
        )
        input = stage_input_files(ctx, input)

        return await self._ensure_context_manager()(name, input, ctx=ctx, **kwargs)


# Global Agent manager instance
agent_manager = AgentManagerServer()
