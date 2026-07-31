"""Done tool for indicating that the task has been completed."""
from typing import Dict, Any
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Indicate that the task has been completed."

_INSTRUCTION = """
## Function
Indicate that the task has been completed.

## Guidance
- Use this tool to signal that a task or subtask has been finished.
- Provide the `result` and `reasoning` of the task in the result and reasoning parameters.

## Parameters
- result (str): The result of the task completion.
- reasoning (str): The analysis or explanation of the task completion.

## Example
{"name": "done_tool", "args": {"reasoning": "The task has been completed successfully.","result": "The task has been completed."}}
"""

@TOOL.register_module(force=True)
class DoneTool(Tool):
    """A tool for indicating that the task has been completed."""

    name: str = "done_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    progress_policy: str = "always"
    
    def __init__(self, enable_evolving: bool = False, **kwargs):
        """A tool for indicating that the task has been completed."""
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, 
                       reasoning: str,
                       result: str,
                       **kwargs) -> Response:
        """
        Indicate that the task has been completed.

        Args:
            reasoning (str): The reasoning of the task completion. Must be provided.
            result (str): The result of the task completion. Must be provided.
        """
        # Convert to string in case LLM returns non-string types
        if reasoning is None or reasoning == "":
            reasoning = "No reasoning provided"
        else:
            reasoning = str(reasoning)
        if result is None or result == "":
            result = "No result provided"
        else:
            result = str(result)
        return Response(type=ResponseType.TOOL, success=True, message=result, data={"reasoning": reasoning, "result": result})
