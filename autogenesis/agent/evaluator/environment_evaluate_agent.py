"""EnvironmentEvaluateAgent — evaluates an existing environment across quality dimensions."""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.response.types import Response
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class EnvironmentEvaluateAgent(Agent):
    """Evaluates an existing environment across quality dimensions and returns a scored report.

    Produces no registrable artifact, so its ``__call__`` just runs the base-class
    standard loop. The target environment is named in the task; the agent should call
    ``inspect_environment_tool`` to obtain its registry facts and file paths before reading it."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="environment_evaluate_agent")
    description: str = Field(
        default="An agent that evaluates an environment across multiple quality dimensions."
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = Field(default=False)

    def __init__(
        self,
        base_dir: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        prompt_name: Optional[str] = None,
        memory_name: Optional[str] = None,
        max_actions: int = 10,
        max_step: int = 20,
        review_steps: int = 5,
        enable_evolving: bool = False,
        **kwargs,
    ):
        super().__init__(
            base_dir=base_dir,
            name=name,
            description=description,
            metadata=metadata,
            model_name=model_name,
            prompt_name=prompt_name or "environment_evaluate_agent",
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )

    async def __call__(
        self,
        task: Optional[str] = None,
        files: Optional[List[str]] = None,
        ctx: Optional[AgentContext] = None,
        **kwargs,
    ) -> Response:
        """Entry point — evaluation produces no registrable artifact, so it runs the
        base-class standard think-and-act loop unchanged."""
        return await super().__call__(task=task, files=files, ctx=ctx, **kwargs)
