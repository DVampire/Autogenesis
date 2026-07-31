"""TEMPLATE — a tool (a callable an agent invokes with a JSON args object).

Copy to `extension/tool/{name}.py`, rename the class, fill the two doc constants and
`__call__`. Docs are split so tool_context stays small (progressive disclosure):
  - `_DESCRIPTION` — one line; all the agent sees in tool_context.
  - `_INSTRUCTION` — the full instruction in FOUR blocks (Function / Guidance /
    Parameters / Example); fetched on demand via `inspect_tool`.
`__call__` must return a `Response` — return `success=False` on expected failures
rather than raising, and do heavyweight imports inside `__call__` to avoid cycles.
"""

from typing import Any, Dict
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "One line: what the tool does."

_INSTRUCTION = """
## Function
What the tool does, in a sentence or two.

## Guidance
When and how to use it; caveats; when NOT to use it.

## Parameters
- arg_name (type): what it is; required vs optional and any default.

## Example
{"name": "my_tool", "args": {"arg_name": "value"}}
"""


@TOOL.register_module(force=True)
class MyTool(Tool):
    """One-line purpose."""

    name: str = "my_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    # enable_evolving=True marks the tool as evolvable (the optimize agent may edit it).
    enable_evolving: bool = Field(default=True, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = True, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, arg_name: str, **kwargs) -> Response:
        """Do the work. Keyword args mirror the ## Parameters block above.

        Accept `ctx` via **kwargs if you need the current session. Prefer giving
        optional args sensible defaults so a missing arg fails gracefully rather
        than raising a TypeError.
        """
        try:
            # --- implementation ---
            result = f"processed: {arg_name}"
            return Response(
                type=ResponseType.TOOL,
                success=True,
                message=result,
                data={"arg_name": arg_name, "result": result},
            )
        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=str(e))
