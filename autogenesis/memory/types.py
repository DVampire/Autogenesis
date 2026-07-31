from datetime import datetime
from typing import Dict, Any, Optional, List, Type
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
import json

from autogenesis.utils import dedent
from autogenesis.dynamic import dynamic_manager
from autogenesis.session import BaseContext


class MemoryContext(BaseContext):
    """Context passed into memory manager operations."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this memory operation.")
    name: Optional[str] = Field(default=None, description="Human-readable label for this memory operation.")
    workspace_root: Optional[str] = Field(default=None, description="Working directory available to the memory system.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload for this memory operation.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this memory context.")
    agent_name: Optional[str] = Field(default=None, description="Name of the agent using this memory context.")
    task_id: Optional[str] = Field(default=None, description="Task identifier for scoping memory reads and writes.")


class EventType(Enum):
    
    # Agent Event Types
    TASK_START = "task_start"
    ACTION_STEP = "action_step"
    TASK_END = "task_end"

class ChatEvent(BaseModel):
    id: str = Field(..., description="The unique identifier for the event.")
    step_number: int = Field(..., description="The step number of the event.")
    event_type: EventType = Field(..., description="The type of the event.")
    timestamp: datetime = Field(default_factory=datetime.now, description="The timestamp of the event.")
    data: Dict[str, Any] = Field(default_factory=dict, description="The data of the event.")
    agent_name: Optional[str] = Field(None, description="The name of the agent that generated the event.")
    session_id: Optional[str] = Field(None, description="The session ID of the event.")
    task_id: Optional[str] = Field(None, description="The task ID of the event.")
    
    def __str__(self):
        string = dedent(f"""<chat_event>
            ID: {self.id}
            Step Number: {self.step_number}
            Event Type: {self.event_type}
            Timestamp: {self.timestamp}
            Agent Name: {self.agent_name}
            Session ID: {self.session_id}
            Task ID: {self.task_id}
            Data: {json.dumps(self.data)}
            </chat_event>""")
        return string
    
    def __repr__(self):
        return self.__str__()

class Importance(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Insight(BaseModel):
    id: str = Field(description="The unique identifier for the insight.")
    content: str = Field(description="The insight content")
    importance: Importance = Field(description="Importance level")
    source_event_id: str = Field(description="ID of the event that generated this insight")
    tags: List[str] = Field(description="Tags for categorization")
    
    def __str__(self):
        string = dedent(f"""<insight>
            ID: {self.id}
            Content: {self.content}
            Importance: {self.importance}
            Source Event ID: {self.source_event_id}
            Tags: {self.tags}
            </insight>""")
        return string
    
    def __repr__(self):
        return self.__str__()

class Summary(BaseModel):
    id: str = Field(description="The unique identifier for the summary.")
    importance: Importance = Field(description="Importance level")
    content: str = Field(description="The summary content")
    
    def __str__(self):
        string = dedent(f"""<summary>
            ID: {self.id}
            Importance: {self.importance}
            Content: {self.content}
            </summary>""")
        return string
    
    def __repr__(self):
        return self.__str__()

class Memory(BaseModel):
    """Base class for all memory systems"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    name: str = Field(default="", description="The name of the memory system")
    description: str = Field(default="", description="The description of the memory system")
    save_path: Optional[str] = Field(default=None, description="Path to save/load memory JSON file")
    enable_evolving: bool = Field(default=False, description="Whether the memory system may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    prompt_readable: bool = Field(default=True, description="Whether get() returns text suitable for prompt injection. Set False for HTML-based memories.")

    def __init__(self, **kwargs):
        """Initialize memory system."""
        super().__init__(**kwargs)
        # Auto-set name from class name if not provided
        if not self.name:
            import inflection
            self.name = inflection.underscore(self.__class__.__name__)
        # Auto-set description from docstring if not provided
        if not self.description and self.__class__.__doc__:
            self.description = self.__class__.__doc__.strip().split('\n')[0]
    
    def __str__(self):
        return f"Memory(name={self.name}, description={self.description})"
    
    def __repr__(self):
        return self.__str__()


class MemoryConfig(BaseModel):
    """Memory configuration for registration"""
    name: str = Field(description="The name of the memory system")
    description: str = Field(description="The description of the memory system")
    enable_evolving: bool = Field(default=False, description="Whether the memory system may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    version: str = Field(default="1.0.0", description="Version of the memory system")
    
    cls: Optional[Type[Memory]] = Field(default=None, description="The class of the memory system")
    instance: Optional[Any] = Field(default=None, description="The instance of the memory system")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="The initialization configuration of the memory system")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="The metadata of the memory system")
    code: Optional[str] = Field(default=None, description="Source code for dynamically generated memory classes (used when cls cannot be imported from a module)")
    
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump the model to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "enable_evolving": self.enable_evolving,
            "permission_mode": self.permission_mode,
            "version": self.version,
            "cls": dynamic_manager.get_class_string(self.cls) if self.cls else None,
            "config": self.config,
            "instance": None,  # Don't serialize instance
            "metadata": self.metadata,
            "code": self.code,
        }
    
    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'MemoryConfig':
        """Validate the model from a dictionary."""
        name = data.get("name")
        description = data.get("description")
        enable_evolving = data.get("enable_evolving", False)
        permission_mode = data.get("permission_mode", "workspace_write")
        version = data.get("version", "1.0.0")
        
        cls_ = None
        code = data.get("code")
        if code:
            class_name = dynamic_manager.extract_class_name_from_code(code)
            if class_name:
                try:
                    cls_ = dynamic_manager.load_class(
                        code, 
                        class_name=class_name,
                        base_class=Memory,
                        context="memory"
                    )
                except Exception as e:
                    cls_ = None
            else:
                cls_ = None
        else:
            cls_ = None
            
        config = data.get("config", {})
        instance = data.get("instance", None)
        metadata = data.get("metadata", {})
        
        return cls(
            name=name,
            description=description,
            enable_evolving=enable_evolving,
            permission_mode=permission_mode,
            version=version,
            cls=cls_,
            config=config,
            instance=instance,
            metadata=metadata,
            code=code,
        )
    
    def __str__(self):
        return f"MemoryConfig(name={self.name}, description={self.description}, version={self.version})"
    
    def __repr__(self):
        return self.__str__()
