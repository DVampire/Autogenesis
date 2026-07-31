from typing import Any, Dict
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Reverse a string and return the reversed result."

_INSTRUCTION = """
## Function
Takes a single string and returns its characters in reverse order. Handles empty strings and unicode text.

## Guidance
Use this tool when you need to reverse the order of characters in a piece of text. It returns the reversed string in the response message and data. An empty string returns an empty string. Reversal is performed by Unicode code point, which is correct for typical text.

## Parameters
- text (str): The input string to reverse.

## Example
{"name": "reverse_string_tool", "args": {"text": "hello"}}
"""


@TOOL.register_module(force=True)
class ReverseStringTool(Tool):
    """Reverse a given string."""
    name: str = "reverse_string_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, text: str = None, **kwargs) -> Response:
        """Reverse the input string and return it in a Response."""
        # Accept common alternative arg name for robustness.
        if text is None:
            text = kwargs.get("input_string")
        if text is None:
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message="Missing required argument 'text' (a string to reverse).",
                data={},
            )
        if not isinstance(text, str):
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message=f"Argument 'text' must be a string, got {type(text).__name__}.",
                data={},
            )
        reversed_text = text[::-1]
        return Response(
            type=ResponseType.TOOL,
            success=True,
            message=reversed_text,
            data={"text": text, "reversed": reversed_text},
        )
