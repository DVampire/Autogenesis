"""GeneralAgent — iterative reasoning and action via tools, skills, connectors, and text."""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.registry import AGENT
from autogenesis.agent.types import Agent, AgentContext
from autogenesis.response.types import Response


@AGENT.register_module(force=True)
class GeneralAgent(Agent):
    """Iterative agent that reasons and acts via tools, skills, connectors, and direct text.

    Carries no bespoke loop or context builder: it uses the base-class standard
    think-and-act loop (``Agent.__call__``) and context builder unchanged, and only
    supplies its own name/description/prompt.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="general_agent")
    description: str = Field(
        default="An iterative agent that reasons and acts by using tools, skills, and direct "
                "responses to accomplish tasks accurately, safely, and efficiently."
    )
    metadata: Dict[str, Any] = Field(default={})
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
            prompt_name=prompt_name or "general_agent",
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
        """Entry point — runs the base-class standard think-and-act loop unchanged."""
        return await super().__call__(task=task, files=files, ctx=ctx, **kwargs)
