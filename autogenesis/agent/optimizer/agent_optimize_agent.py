"""AgentOptimizeAgent — evolves an existing agent (Python class and/or HTML prompt) given an optimization task."""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.response.types import Response
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class AgentOptimizeAgent(Agent):
    """Evolves an existing agent to satisfy an optimization task.

    Can modify the Python class file, the HTML prompt file, or both. Runs the
    base-class standard loop, then reloads and re-registers the edited agent inline
    in ``__call__`` once the loop finishes.

    The target agent is named in the task text. The agent should call
    ``inspect_agent_tool`` first to confirm the target is registered and evolvable
    (``enable_evolving=True``) and to obtain its file paths — a frozen agent
    (enable_evolving=False) must NOT be optimized.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="agent_optimize_agent")
    description: str = Field(
        default="An agent that evolves an existing agent (Python class and/or HTML prompt) given an optimization task."
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
        max_step: int = 30,
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
            prompt_name=prompt_name or "agent_optimize_agent",
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )

    async def _finalize_run(self, response, ctx):
        """Run the base loop, then reload and re-register the edited agent.

        The registration hook locates the edited files by scanning the agent's
        final done_tool reasoning for their paths, so those paths MUST appear there.
        """
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent
        from autogenesis.sandbox.project import staged_extension_root

        # Reload and re-register the edited agent now that the loop has finished.
        if response.success:
            result = await hook_manager(
                name="agent_registration_hook",
                input={
                    "event": HookEvent.ON_STOP,
                    "reasoning": (response.data or {}).get("reasoning") or "",
                    "extension_root": staged_extension_root(ctx),
                    "model_name": self.model_name,
                },
                ctx=ctx,
            )
            if result.decision == HookDecision.BLOCK:
                response.success = False
                response.message = result.reason or (
                    "Re-registration failed; include the edited file path in the "
                    "done_tool reasoning."
                )
        return response
