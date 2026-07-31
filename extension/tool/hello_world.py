"""Hello World tool — a minimal example tool in extension/tool/."""
import datetime
from typing import Any, Dict, Optional
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL


@TOOL.register_module(force=True)
class HelloWorldTool(Tool):
    """A simple hello world tool that returns a greeting message."""

    name: str = "hello_world_tool"
    description: str = (
        "A simple hello world tool. Returns a greeting for the given name.\n"
        "Args:\n"
        "- name (str): The name to greet. Defaults to 'World'."
    )
    metadata: Dict[str, Any] = Field(default={})
    enable_evolving: bool = Field(default=True)

    def __init__(self, enable_evolving: bool = True, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, name: Optional[str] = "World", **kwargs) -> Response:
        """Return a greeting for the given name.

        Args:
            name (str): The name to greet.
        """
        timestamp = datetime.datetime.now().isoformat()
        message = f"Hello, {name}! (Timestamp: {timestamp})"
        return Response(type=ResponseType.TOOL, 
            success=True,
            message=message,
            data={"greeting": message, "timestamp": timestamp},
        )
