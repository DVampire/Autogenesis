"""Memory Manager

Manager implementation for the Memory Context Protocol.
"""
import os
from typing import Any, Dict, List, Optional, Union, Type

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.utils import assemble_workspace_path
from autogenesis.logger import logger
from autogenesis.memory.types import MemoryConfig, Memory
from autogenesis.session import SessionContext
from autogenesis.memory.context import MemoryContextManager

class MemoryManagerServer(BaseModel):
    """Memory Manager Server for managing memory system registration and lifecycle"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="The base directory to use for the memory systems")
    
    def __init__(self, **kwargs):
        """Initialize the Memory Manager."""
        super().__init__(**kwargs)
        self._registered_memories: Dict[str, MemoryConfig] = {}  # memory_name -> MemoryConfig
    
    async def initialize(self, memory_names: Optional[List[str]] = None):
        """Initialize memory systems by discovering and registering them (similar to tool).
        
        Args:
            memory_names: List of memory system names to initialize. If None, initialize all discovered memory systems.
        """
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "memory"))
        logger.info(f"| 📁 Memory Manager base directory: {self.base_dir}")
        
        # Initialize memory context manager
        self.memory_context_manager = MemoryContextManager(
            base_dir=self.base_dir,
        )
        await self.memory_context_manager.initialize(memory_names=memory_names)

        logger.info("| ✅ Memory systems initialization completed")

    def rebind(self, log_root: str) -> None:
        """Re-point this manager and its live memory systems at ``<log_root>/memory``.

        Long-lived hosts (the Gateway) initialize memory once, before any session
        exists; binding a session re-points it so each session's memory files land
        under that session's own log root.
        """
        base_dir = assemble_workspace_path(os.path.join(log_root, "memory"))
        self.base_dir = base_dir
        ctx_manager = getattr(self, "memory_context_manager", None)
        if ctx_manager is None:
            return
        ctx_manager.base_dir = base_dir
        for memory_config in getattr(ctx_manager, "_memory_configs", {}).values():
            instance = getattr(memory_config, "instance", None)
            if instance is not None and hasattr(instance, "base_dir"):
                instance.base_dir = base_dir
    
    async def register(self, memory: Union[Memory, Type[Memory]], *, override: bool = False, **kwargs: Any) -> MemoryConfig:
        """Register a memory system or memory class asynchronously.
        
        Args:
            memory: Memory instance or class to register
            override: Whether to override existing registration
            **kwargs: Configuration for memory initialization
            
        Returns:
            MemoryConfig: Memory configuration
        """
        memory_config = await self.memory_context_manager.register(memory, override=override, **kwargs)
        self._registered_memories[memory_config.name] = memory_config
        return memory_config
    
    async def update(self, memory_name: str, memory: Union[Memory, Type[Memory]], 
                    new_version: Optional[str] = None, description: Optional[str] = None,
                    **kwargs: Any) -> MemoryConfig:
        """Update an existing memory system with new configuration and create a new version
        
        Args:
            memory_name: Name of the memory system to update
            memory: New memory instance or class with updated content
            new_version: New version string. If None, auto-increments from current version.
            description: Description for this version update
            **kwargs: Configuration for memory initialization
            
        Returns:
            MemoryConfig: Updated memory configuration
        """
        memory_config = await self.memory_context_manager.update(memory_name, memory, new_version, description, **kwargs)
        self._registered_memories[memory_config.name] = memory_config
        return memory_config
    
    async def get_info(self, memory_name: str) -> Optional[MemoryConfig]:
        """Get memory configuration by name
        
        Args:
            memory_name: Memory system name
            
        Returns:
            MemoryConfig: Memory configuration or None if not found
        """
        return await self.memory_context_manager.get_info(memory_name)
    
    async def unregister(self, memory_name: str) -> bool:
        """Unregister a memory system.

        Exposed so an evolved memory component can be unloaded or rolled back
        through ExtensionManager, the same way tools and environments are.

        Args:
            memory_name: Memory system name

        Returns:
            bool: True if unregistered successfully, False otherwise
        """
        return await self.memory_context_manager.unregister(memory_name)

    async def list(self) -> List[str]:
        """List all registered memory systems

        Returns:
            List[str]: List of memory system names
        """
        return await self.memory_context_manager.list()
    
    async def get(self, memory_name: str) -> Memory:
        """Get memory system instance by name (similar to tool_manager.get()).
        
        Note: Unlike tools, memory systems create a new instance each time since each agent
        needs its own memory system instance to manage its own sessions.
        
        Args:
            memory_name: Memory system name
            
        Returns:
            Memory: Memory system instance (new instance each time)
        """
        return await self.memory_context_manager.get(memory_name)
    
    async def cleanup(self):
        """Cleanup all memory systems using context manager."""
        if hasattr(self, 'memory_context_manager'):
            await self.memory_context_manager.cleanup()
            
    async def start_session(self, 
                            memory_name: str, 
                            agent_name: Optional[str] = None,
                            task_id: Optional[str] = None, 
                            description: Optional[str] = None,
                            ctx: SessionContext = None,
                            **kwargs) -> str:
        """Start a memory session.
        
        Args:
            memory_name: Name of the memory system
            agent_name: Optional agent name
            task_id: Optional task ID
            description: Optional description
            ctx: Memory context
            
        Returns:
            Session ID
        """
        return await self.memory_context_manager.start_session(
            memory_name,
            agent_name,
            task_id,
            description,
            ctx=ctx,
            **kwargs
        )
    
    async def add_event(self, 
                        memory_name: str,
                        step_number: int, 
                        event_type: Any, data: Any,
                        agent_name: str, 
                        task_id: Optional[str] = None, 
                        ctx: SessionContext = None,
                        **kwargs):
        """Add an event to memory.
        
        Args:
            memory_name: Name of the memory system
            step_number: Step number
            event_type: Event type
            data: Event data
            agent_name: Agent name
            task_id: Optional task ID
            ctx: Memory context
            **kwargs: Additional arguments
        """
        return await self.memory_context_manager.add_event(
            memory_name,
            step_number,
            event_type,
            data,
            agent_name,
            task_id,
            ctx=ctx,
        **kwargs)
    
    async def end_session(self, 
                          memory_name: str, 
                          ctx: SessionContext = None,
                          **kwargs):
        """End a memory session.
        
        Args:
            memory_name: Name of the memory system
            ctx: Memory context
        """
        return await self.memory_context_manager.end_session(
            memory_name, 
            ctx=ctx,
        **kwargs)
    
    async def get_session_info(self, 
                               memory_name: str, 
                               ctx: SessionContext = None,
                               **kwargs):
        """Get session info.
        
        Args:
            memory_name: Name of the memory system
            ctx: Memory context
            
        Returns:
            SessionInfo or None
        """
        return await self.memory_context_manager.get_session_info(memory_name, ctx=ctx, **kwargs)
    
    async def clear_session(self, 
                            memory_name: str, 
                            ctx: SessionContext = None,
                            **kwargs):
        """Clear a memory session.
        
        Args:
            memory_name: Name of the memory system
            ctx: Memory context
        """
        return await self.memory_context_manager.clear_session(memory_name, ctx=ctx, **kwargs)
    
    async def get_state(self, 
                        name: str, 
                        n: Optional[int] = None, 
                        ctx: SessionContext = None,
                        **kwargs
                        ) -> Dict[str, Any]:
        """Get memory state (events, summaries, insights) for a memory system.
        
        Args:
            name: Memory system name
            n: Number of items to retrieve. If None, returns all items.
            ctx: Memory context
        Returns:
            Dictionary containing 'events', 'summaries', and 'insights'
        """
        return await self.memory_context_manager.get_state(name, n, ctx, **kwargs)
    

# Global Memory Manager Server instance
memory_manager = MemoryManagerServer()
