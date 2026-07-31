"""Optimize and re-register an evolvable HTML Workflow."""

from typing import Any, Dict, Optional
from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent
from autogenesis.agent.generator.workflow_generate_agent import _register_workflow
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class WorkflowOptimizeAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    name: str = Field(default="workflow_optimize_agent")
    description: str = Field(default="Improves an existing evolvable Workflow from execution evidence.")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = False

    def __init__(self, base_dir: str, prompt_name: Optional[str] = None, **kwargs):
        super().__init__(base_dir=base_dir, prompt_name=prompt_name or "workflow_optimize_agent", **kwargs)

    async def _finalize_run(self, response, ctx):
        """Re-register the improved Workflow before the caller's reply is resolved."""
        return await _register_workflow(response, ctx, self.model_name)
