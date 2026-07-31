"""TEMPLATE — a tool-calling agent (LLM think-and-act loop).

Copy to `extension/agent/{name}.py`, rename the class, fill name/description, and
pair it with an HTML prompt at `extension/prompt/{name}.html` (see
`html_prompt_template.html`). This is the common agent type: it reasons and acts
step by step using tools/skills/connectors, driven by the base-class loop.

KEY RULE — the class is THIN. The base `Agent` already implements the full
standard loop (`__call__`) and context builder (`_get_agent_context`,
`_get_messages`, `_think_and_act`). Inherit all of it. Do NOT re-implement the
loop or override the context methods unless the agent truly needs bespoke behavior
(that is a red flag reviewers look for). Supply identity + prompt; inherit the rest.
"""

from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from autogenesis.registry import AGENT
from autogenesis.agent.types import Agent


@AGENT.register_module(force=True)
class MyAgent(Agent):
    """One-line purpose — what this agent does and when it is dispatched."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="my_agent")
    description: str = Field(
        default="What this agent does AND when to use it (the description is how it gets chosen)."
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # enable_evolving=True marks the agent as evolvable (the optimize agent may edit it).
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
            prompt_name=prompt_name or "my_agent",  # must match the HTML prompt's <meta name="name">
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )
