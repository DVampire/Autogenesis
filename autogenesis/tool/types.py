from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from autogenesis.dynamic import dynamic_manager
from autogenesis.session import BaseContext
from autogenesis.response.types import Response, ResponseType


class ToolContext(BaseContext):
    """Context passed into tool manager and individual tool instances."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this tool call.")
    name: str = Field(default="", description="Name of the tool being called.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the tool.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this tool context.")


class Tool(BaseModel):
    """Base class for all tools that can be exposed through function calling."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="The name of the tool")
    description: str = Field(description="The description of the tool")
    instruction: str = Field(default="", description="Full instruction (function/guidance/parameters/example) fetched on demand via inspect_tool")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    progress_policy: Optional[Literal["workspace", "external", "polling", "always"]] = Field(
        default=None,
        description="No-progress policy: workspace / external / polling / always",
    )

    async def __call__(self, **kwargs) -> Response:
        """Call the tool with the given arguments."""
        raise NotImplementedError("All tools must implement __call__")

class ToolConfig(BaseModel):
    """Tool configuration"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    name: str = Field(description="The name of the tool")
    description: str = Field(description="The description of the tool")
    instruction: str = Field(default="", description="Full instruction (function/guidance/parameters/example); kept out of the prompt context and fetched on demand via inspect_tool")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    progress_policy: Optional[Literal["workspace", "external", "polling", "always"]] = Field(
        default=None, description="No-progress guard policy"
    )
    version: str = Field(default="1.0.0", description="Version of the tool")

    cls: Optional[Type[Tool]] = Field(default=None, description="The class of the tool")
    config: Optional[Dict[str, Any]] = Field(default={}, description="The initialization configuration of the tool")
    instance: Optional[Tool] = Field(default=None, description="The instance of the tool")
    code: Optional[str] = Field(default=None, description="Source code for dynamically generated tool classes (used when cls cannot be imported from a module)")
    path: Optional[str] = Field(default=None, description="Absolute path to the tool's source file")
    
    # Default representations
    function_calling: Optional[Dict[str, Any]] = Field(default=None, description="Default function calling representation")
    text: Optional[str] = Field(default=None, description="Default text representation")
    args_schema: Optional[Type[BaseModel]] = Field(default=None, description="Default args schema (BaseModel type)")

    @model_validator(mode="after")
    def _fill_instruction_from_cls(self) -> "ToolConfig":
        """Backfill `instruction` from the tool class when not explicitly set.

        Lets every ToolConfig construction site (which all pass `cls`) pick up the
        tool's `instruction` field without threading it through each call.
        """
        if not self.instruction and self.cls is not None:
            try:
                field = self.cls.model_fields.get("instruction")
                if field is not None and field.default:
                    self.instruction = field.default
            except Exception:
                pass
        return self

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump the model to a dictionary, recursively serializing nested Pydantic models."""
        
        result = {
            "name": self.name,
            "description": self.description,
            "instruction": self.instruction,
            "metadata": self.metadata,
            "enable_evolving": self.enable_evolving,
            "permission_mode": self.permission_mode,
            "progress_policy": self.progress_policy,
            "version": self.version,

            "cls": dynamic_manager.get_class_string(self.cls) if self.cls else None,
            "config": self.config,
            "instance": None,
            "code": self.code,
            "path": self.path,

            "function_calling": self.function_calling,
            "text": self.text,
            "args_schema": dynamic_manager.serialize_args_schema(self.args_schema) if self.args_schema else None,
        }
        
        return result
    
    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'ToolConfig':
        """Validate the model from a dictionary."""
        name = data.get("name")
        description = data.get("description")
        instruction = data.get("instruction", "")
        metadata = data.get("metadata")
        enable_evolving = data.get("enable_evolving", False)
        permission_mode = data.get("permission_mode", "workspace_write")
        progress_policy = data.get("progress_policy")
        version = data.get("version")
        
        cls_ = None
        code = data.get("code")
        if code:
            class_name = dynamic_manager.extract_class_name_from_code(code)
            if class_name:
                try:
                    cls_ = dynamic_manager.load_class(
                        code, 
                        class_name=class_name,
                        base_class=Tool,
                        context="tool"
                    )
                except Exception as e:
                    cls_ = None
            else:
                cls_ = None
        else:
            cls_ = None
            
        config = data.get("config")
        instance = data.get("instance", None)

        function_calling = data.get("function_calling")
        text = data.get("text")
        args_schema = dynamic_manager.deserialize_args_schema(data.get("args_schema"))
        
        return cls(name=name,
            description=description,
            instruction=instruction,
            metadata=metadata,
            enable_evolving=enable_evolving,
            permission_mode=permission_mode,
            progress_policy=progress_policy,
            version=version,
            cls=cls_,
            config=config,
            instance=instance,
            code=code,
            function_calling=function_calling,
            text=text,
            args_schema=args_schema,
        )

__all__ = [
    "Tool",
    "ToolConfig",
    "ToolContext",
]
