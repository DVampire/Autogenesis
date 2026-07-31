"""Inspect tool — fetch a registered tool's full instruction + registry facts on demand."""
import os
from typing import Dict, Any
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.tool.server import tool_manager
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Fetch a registered tool's full instruction plus its live registry facts (version, evolvability/enable_evolving, source file path) by name."

_INSTRUCTION = """
## Function
Fetch a registered tool's full instruction (function, guidance, parameters, examples) plus its live registry facts (version, evolvability/enable_evolving, source file path).

## Guidance
- The tool context lists only each tool's name and one-line description. Before calling a tool whose arguments you are unsure of, call inspect_tool to read its full instruction.
- When optimizing or evaluating a tool: the registry facts give you its source file path (to read/edit) and its `enable_evolving` — optimization requires enable_evolving=True; a frozen tool (enable_evolving=False) must NOT be edited.
- Pass the exact tool name as shown in the tool context.

## Parameters
- name (str): The exact name of the tool to inspect.

## Example
{"name": "inspect_tool", "args": {"name": "bash_tool"}}
"""


@TOOL.register_module(force=True)
class InspectTool(Tool):
    """A tool that returns another registered tool's full instruction on demand."""

    name: str = "inspect_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, name: str, **kwargs) -> Response:
        """Return the full instruction of the named tool.

        Args:
            name (str): The exact name of the tool to inspect.
        """
        info = await tool_manager.get_info(name)
        if info is None:
            available = await tool_manager.list()
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message=f"Tool '{name}' not found. Available tools: {available}",
            )

        instruction = (getattr(info, "instruction", "") or "").strip()
        if not instruction:
            # No authored instruction — fall back to the short description.
            instruction = f"## Function\n{info.description}"

        # Registry facts — used by tool optimize/evaluate agents (source path + evolvability).
        path = getattr(info, "path", None)
        enable_evolving = bool(getattr(info, "enable_evolving", False))
        version = getattr(info, "version", "")
        facts = (
            "\n\n## Registry Facts\n"
            f"- **Registered**: True\n"
            f"- **Version**: {version}\n"
            f"- **Evolvable (enable_evolving)**: {enable_evolving}\n"
            f"- **Source File**: `{path}`"
            + (f" (exists: {os.path.exists(path)})" if path else " (unknown — not a file-backed tool)")
        )

        schema_json = await tool_manager.get_schema(name, format="json")
        schema_md = await tool_manager.get_schema(name, format="md")
        return Response(
            type=ResponseType.TOOL,
            success=True,
            message=instruction + facts + (f"\n\n{schema_md}" if schema_md else ""),
            data={"tool": name, "registered": True, "enable_evolving": enable_evolving, "path": path, "schema": schema_json},
        )
