"""Inspect a registered HTML workflow without expanding every definition in prompts."""

import os
from typing import Any, Dict, List

from pydantic import Field

from autogenesis.registry import TOOL
from autogenesis.response.types import Response, ResponseType
from autogenesis.tool.types import Tool


_DESCRIPTION = "Fetch a registered workflow's full HTML definition, contract, and live registry facts by name."

_INSTRUCTION = """
## Function
Inspect one registered HTML workflow, including its version, status, applicability,
input/output contract, compiled node tree, source path, and complete HTML definition.

## Guidance
- Registered active workflows are callable directly as `workflow__<name>`.
- Call this tool only when the compact workflow roster is insufficient.
- Evaluation, optimization, and rollback belong to the shared evolution lifecycle;
  this inspection tool is deliberately read-only.

## Parameters
- name (str): Exact registered workflow name.

## Example
{"name": "inspect_workflow", "args": {"name": "parallel_review"}}
"""


def _step_summary(steps) -> List[Dict[str, Any]]:
    """Return a stable, JSON-friendly view of the compiled execution tree."""
    return [
        {
            "id": step.id,
            "type": step.type.value,
            "target": step.target,
            "children": _step_summary(step.children),
            "else_children": _step_summary(step.else_children),
        }
        for step in steps
    ]


@TOOL.register_module(force=True)
class InspectWorkflow(Tool):
    """Read-only progressive disclosure for the Workflow registry."""

    name: str = "inspect_workflow"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = False

    async def __call__(self, name: str, **kwargs) -> Response:
        from autogenesis.workflow import workflow_manager  # avoid import cycle at startup

        definition = workflow_manager.get_info(name)
        if definition is None:
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message=f"Workflow {name!r} not found. Available workflows: {workflow_manager.list()}",
                data={"workflow": name, "registered": False},
            )

        path = definition.source_path
        inputs = {key: value.model_dump() for key, value in definition.inputs.items()}
        nodes = _step_summary(definition.program)
        summary = workflow_manager.evaluation_summary(name)
        evaluations = [item.model_dump() for item in workflow_manager.evaluations(name)]
        schema_json = await workflow_manager.get_schema(name, format="json")
        schema_md = await workflow_manager.get_schema(name, format="md")
        facts = (
            f"## Registry Facts\n"
            f"- **Workflow**: `{definition.name}`\n"
            f"- **Registered**: True\n"
            f"- **Version**: {definition.version}\n"
            f"- **Schema Version**: {definition.schema_version}\n"
            f"- **Program Hash**: `{definition.program_hash}`\n"
            f"- **Status**: {definition.status.value}\n"
            f"- **Evolvable (enable_evolving)**: {definition.enable_evolving}\n"
            f"- **Source File**: `{path}`"
            + (f" (exists: {os.path.exists(path)})" if path else " (in-memory definition)")
            + f"\n- **Tags**: {definition.tags or 'none'}\n"
            f"- **Applicability**: {definition.applicability or 'not specified'}\n"
            f"- **Inputs**: {inputs}\n"
            f"- **Outputs**: {definition.outputs}\n"
            f"- **Evaluation Summary**: {summary}\n\n"
            f"- **Recorded Evaluations**: {len(evaluations)}\n\n"
            f"## Compiled Nodes\n{nodes}\n\n"
            f"## HTML Definition\n```html\n{definition.source.strip()}\n```"
            + (f"\n\n{schema_md}" if schema_md else "")
        )
        return Response(
            type=ResponseType.TOOL,
            success=True,
            message=facts,
            data={
                "workflow": name,
                "registered": True,
                "version": definition.version,
                "program_hash": definition.program_hash,
                "status": definition.status.value,
                "enable_evolving": definition.enable_evolving,
                "source_path": path,
                "inputs": inputs,
                "outputs": definition.outputs,
                "nodes": nodes,
                "html": definition.source,
                "evaluation_summary": summary,
                "evaluations": evaluations,
                "schema": schema_json,
            },
        )
