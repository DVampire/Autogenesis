"""Evolution tool — manage the version lifecycle of evolved (extension) components.

The generate/optimize agents *create* new versions; this tool lets an agent (the
MetaAgent, driven by a reviewer verdict) **undo** them: list what is active, list a
component's archived versions, roll back to a previous version, or unload a component
entirely. This is the "undo" lever that makes a regression caught by `reviewer_agent`
actionable — restore the last good version instead of only re-optimizing.

Only affects evolved components under `extension/`; built-in `src/` capabilities are
never touched. Rollback restores an archived version over the active file and
re-registers it (it is a legitimate restore, not an evolution-overwrite, so it is not
subject to the enable_evolving gate).
"""

from typing import Any, Dict

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Manage evolved (extension) components: list active, list versions, roll back, or unload."

_INSTRUCTION = """
## Function
Manage the version lifecycle of evolved components (tools/agents/prompts/skills/environments/connectors/workflows created or optimized under `extension/`). Use it to UNDO a bad evolution a reviewer flagged — roll back to the previous good version, or unload a newly generated component that made things worse.

## Actions (pass `action`)
- `list_active`: list all active evolved components (module, name, version). No args.
- `list_versions`: list archived versions of one component. Args: `module`, `name`.
- `diff`: show the source diff between two versions (see what an optimization actually changed). Args: `module`, `name`, `version_a`, `version_b` (optional; defaults to the live version).
- `rollback`: restore a component to a previous version (becomes live immediately). Args: `module`, `name`, `version`.
- `unload`: unregister an evolved component (its archive is kept). Args: `module`, `name`.
- `record_workflow_evaluation`: append one version-scoped Workflow evaluation. Successful evidence requires a real terminal `run_id`; static failures require `case_id`. Args: `name`, `version`, `success`, `quality_score`, plus optional `run_id`, `case_id`, `token_cost`, `elapsed_ms`, `notes`.

`module` is one of: tool | agent | prompt | skill | environment | connector | workflow.

## Guidance
- Pair with `reviewer_agent`: if the reviewer's verdict is that an evolution regressed the outcome, `rollback` to the prior version (use `list_versions` first to see what to roll back to), or `unload` a brand-new component that has no prior good version.
- Only affects `extension/` components; built-in capabilities cannot be rolled back/unloaded here.
- A rollback/unload takes effect for the NEXT dispatched sub-agent, not one already running.

## Example
{"name": "evolution_tool", "args": {"action": "rollback", "module": "tool", "name": "calculator_tool", "version": "1.0.0"}}
"""


@TOOL.register_module(force=True)
class EvolutionTool(Tool):
    """List/rollback/unload evolved extension components (the evolution undo lever)."""

    name: str = "evolution_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Mutates the active set of evolved components under extension/.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, action: str = "list_active", **kwargs) -> Response:
        from autogenesis.extension import extension_manager  # local import avoids a heavy import at load
        action = (action or "list_active").lower().strip()
        try:
            if action == "list_active":
                comps = extension_manager.read_manifest().components
                if not comps:
                    return Response(type=ResponseType.TOOL, success=True, message="No evolved components active.")
                body = "\n".join(["module\tname\tversion\tfile"] +
                                 [f"{c.module}\t{c.name}\t{c.version}\t{c.file}" for c in comps])
                return Response(type=ResponseType.TOOL, success=True, message=body,
                                data={"components": [c.model_dump() for c in comps]})

            if action == "list_versions":
                module, name = kwargs["module"], kwargs["name"]
                vers = extension_manager.list_component_versions(module, name)
                if not vers:
                    return Response(type=ResponseType.TOOL, success=False,
                                    message=f"No archived versions for {module}:{name}.")
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"{module}:{name} versions: {', '.join(vers)}",
                                data={"module": module, "name": name, "versions": vers})

            if action == "diff":
                module, name, version_a = kwargs["module"], kwargs["name"], kwargs["version_a"]
                version_b = kwargs.get("version_b")
                diff = extension_manager.diff_versions(module, name, version_a, version_b)
                return Response(type=ResponseType.TOOL, success=True, message=diff,
                                data={"module": module, "name": name, "version_a": version_a, "version_b": version_b})

            if action == "rollback":
                module, name, version = kwargs["module"], kwargs["name"], kwargs["version"]
                restored = await extension_manager.rollback(module, name, version)
                logger.info(f"| ⏪ evolution_tool: rolled back {module}:{restored} to v{version}")
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"Rolled back {module}:{restored} to v{version} (live on next dispatch).",
                                data={"module": module, "name": restored, "version": version})

            if action == "unload":
                module, name = kwargs["module"], kwargs["name"]
                ok = await extension_manager.unload(module, name)
                return Response(type=ResponseType.TOOL, success=bool(ok),
                                message=(f"Unloaded {module}:{name}." if ok else f"{module}:{name} was not active."),
                                data={"module": module, "name": name, "unloaded": bool(ok)})

            if action == "record_workflow_evaluation":
                from autogenesis.workflow import WorkflowEvaluation, workflow_manager
                raw_success = kwargs["success"]
                success = (
                    raw_success if isinstance(raw_success, bool)
                    else str(raw_success).strip().lower() in {"true", "1", "yes"}
                )
                evaluation = WorkflowEvaluation(
                    workflow_name=kwargs["name"], workflow_version=kwargs["version"],
                    run_id=kwargs.get("run_id"), case_id=kwargs.get("case_id"), success=success,
                    quality_score=float(kwargs["quality_score"]),
                    token_cost=int(kwargs.get("token_cost", 0)),
                    elapsed_ms=float(kwargs.get("elapsed_ms", 0.0)), notes=kwargs.get("notes", ""),
                )
                workflow_manager.record_evaluation(evaluation)
                summary = workflow_manager.evaluation_summary(evaluation.workflow_name)
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"Recorded evaluation for workflow:{evaluation.workflow_name}. Summary: {summary}",
                                data={"evaluation": evaluation.model_dump(), "summary": summary})

            return Response(type=ResponseType.TOOL, success=False,
                            message=f"Unknown action {action!r}. Use list_active | list_versions | diff | rollback | unload | record_workflow_evaluation.")
        except KeyError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Missing required arg: {e}")
        except Exception as e:
            logger.error(f"| ❌ evolution_tool {action} failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {e}")
