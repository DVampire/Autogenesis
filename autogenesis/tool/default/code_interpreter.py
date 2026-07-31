"""Code interpreter tool — runs code in the project's live kernel.

Like every other tool this runs in the base environment: the agent system and
its tools ship together, so there is nothing to route anywhere. Execution goes
to a Jupyter kernel held open per project (see ``autogenesis.kernel``), which
is what makes state persist — a later call sees the variables an earlier one
defined.

It used to start a peer container of its own. That bought no isolation the
agent did not already have (``bash_tool`` runs here too) and cost it the thing
that mattered: the container mounted nothing, so code could not read the files
the agent had just written into the workspace.
"""

from typing import Any, Dict, Optional

from pydantic import Field

from autogenesis.kernel import kernel_manager
from autogenesis.logger import logger
from autogenesis.registry import TOOL
from autogenesis.response.types import Response, ResponseType
from autogenesis.tool.types import Tool

_DESCRIPTION = "Execute code in a persistent interpreter and return everything it produced."

_INSTRUCTION = """
## Function
Execute code in a persistent interpreter and return everything it produced.

## Guidance
State persists across calls: variables, imports and open files from one call are
still there in the next. The interpreter starts in the workspace, so relative
paths mean what they mean to bash and to the files pane — code can read the
files you just wrote.

Figures come back as images rather than as `<Figure ...>`: plot with matplotlib
and the picture is captured alongside the text.

## Parameters
- code (str): The code to execute.
- language (str, optional): One of python (default), bash, javascript, typescript, r.

## Example
{"name": "code_interpreter_tool", "args": {"code": "print(2 + 2)", "language": "python"}}
"""

#: Language name -> kernelspec. Unlisted names pass through, so a kernel
#: installed in the image is reachable by its own name without editing this.
_KERNELS = {
    "python": "python3", "python3": "python3", "py": "python3",
    "bash": "bash", "sh": "bash",
    "javascript": "jslab", "js": "jslab",
    "typescript": "tslab", "ts": "tslab",
    "r": "ir",
}


def kernel_for(language: str) -> Optional[str]:
    return _KERNELS.get((language or "python").strip().lower(), language)


@TOOL.register_module(force=True)
class CodeInterpreterTool(Tool):
    """Execute code in the project's persistent, multi-language interpreter."""

    name: str = "code_interpreter_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="danger_full_access", description="Runs code in the project's kernel.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, code: str, language: str = "python", **kwargs) -> Response:
        """Execute ``code`` in this project's kernel."""
        ctx = kwargs.get("ctx")
        # Keyed by project, not by ctx.id: ctx.id is the *state* scope — one per
        # conversation, one per workflow run — so keying the interpreter off it
        # would hand every new line of dialogue a blank one. The kernel is a
        # resource, shared like the project's files.
        extra = getattr(ctx, "extra", None) or {}
        key = extra.get("project_id") or getattr(ctx, "id", None) or "default"

        result = await kernel_manager.execute(
            code, key=key, kernel_name=kernel_for(language), language=language,
            # The project's workspace, so the kernel starts where bash starts and
            # relative paths mean the same thing to both.
            workspace=getattr(ctx, "workspace_root", None), origin="agent")
        logger.info(f"| {'✅' if result.success else '⚠️'} code_interpreter ran {language} code")
        return Response(
            type=ResponseType.TOOL,
            success=result.success,
            message=result.as_message(),
            data={
                "execution_count": result.execution_count,
                "error": result.error,
                # Every output in order with its MIME bundle intact, so a
                # notebook view can render the figures the message can only name.
                "outputs": [output.model_dump(mode="json") for output in result.outputs],
            },
        )
