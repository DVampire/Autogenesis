"""Evaluate one live Workflow version; it never edits artifacts."""

from typing import Any, Dict, Optional
from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class WorkflowEvaluateAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    name: str = Field(default="workflow_evaluate_agent")
    description: str = Field(default="Evaluates a Workflow for safety, quality, reliability, and efficiency.")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = False
    permission_mode: str = Field(default="read_only")

    def __init__(self, base_dir: str, prompt_name: Optional[str] = None, **kwargs):
        super().__init__(base_dir=base_dir, prompt_name=prompt_name or "workflow_evaluate_agent", **kwargs)

    def _include_workflows(self) -> bool:
        """Expose only Workflow callables, without granting sub-agent orchestration."""
        return True

    def _allow_read_only_tool_call(self, name: str, input: Dict[str, Any]) -> bool:
        """Permit the one mutating call this read-only evaluator needs: recording its
        own evaluation verdict via ``evolution_tool``. Everything else stays blocked."""
        return name == "evolution_tool" and input.get("action") == "record_workflow_evaluation"

    def _target_capability_allowlists(self, target_name: Optional[str]) -> Dict[str, Any]:
        """Scope this run to the single Workflow under evaluation, so the agent can only
        see and invoke that target."""
        return {"workflow_allowlist": [target_name]} if target_name else {}

    async def _get_workflow_context(self, ctx: AgentContext, **kwargs) -> Dict[str, Any]:
        """Render the allowlisted Workflow's instruction into the prompt context.

        Reads the ``workflow_allowlist`` from ``ctx.extra`` and asks the workflow manager
        for its instruction text, so the evaluator prompt describes exactly the Workflow
        being assessed.
        """
        from autogenesis.workflow import workflow_manager

        allowlist = (getattr(ctx, "extra", None) or {}).get("workflow_allowlist")
        content = workflow_manager.get_instruction(allowlist=allowlist)
        available = content or "[No workflows loaded.]"
        return {
            "workflow_context": f"### Available Workflows\n{available}",
            "available_workflows": available,
        }
