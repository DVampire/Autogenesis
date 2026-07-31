"""MemoryOptimizeAgent — evolves an existing memory given an evolution task."""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.response.types import Response
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class MemoryOptimizeAgent(Agent):
    """Evolves an existing memory (Python class and/or config) to satisfy an evolution task.

    Runs the base-class standard loop, then re-registers the edited memory inline in
    ``__call__``. The target memory is named in the task; the agent should call
    ``inspect_memory_tool`` first to confirm it is registered and evolvable
    (enable_evolving=True) and to obtain its file paths — a frozen memory must NOT be optimized."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="memory_optimize_agent")
    description: str = Field(
        default="An agent that evolves an existing memory (Python class and/or config) given an evolution task."
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
            prompt_name=prompt_name or "memory_optimize_agent",
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )

    async def _finalize_run(self, response, ctx):
        """Run the base loop, then reload and re-register the edited memory."""
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent
        from autogenesis.sandbox.project import staged_extension_root

        if response.success:
            result = await hook_manager(
                name="memory_registration_hook",
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
                response.message = result.reason or "Re-registration failed; include the edited memory file path in the done_tool reasoning."
        return response
