from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from autogenesis.registry import AGENT
from autogenesis.agent.types import Agent


@AGENT.register_module(force=True)
class GaiaAnswerAgent(Agent):
    """Turns a computed value plus a format contract into the exact submission string."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="gaia_answer_agent")
    description: str = Field(
        default="Use this agent to format a computed answer into the exact final submission string according to the GAIA question's format contract."
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = Field(default=True)

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
        enable_evolving: bool = True,
        **kwargs,
    ):
        super().__init__(
            base_dir=base_dir,
            name=name,
            description=description,
            metadata=metadata,
            model_name=model_name,
            prompt_name=prompt_name or "gaia_answer_agent",
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )
