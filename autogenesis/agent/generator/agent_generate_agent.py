"""AgentGenerateAgent — generates a new agent (Python class + optional HTML prompt) from a description."""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.response.types import Response
from autogenesis.registry import AGENT


@AGENT.register_module(force=True)
class AgentGenerateAgent(Agent):
    """Generates a new agent (Python class + optional HTML prompt) from a natural-language description.

    Tool-calling agents → Python class + HTML prompt + config dict (3 files).
    Procedural agents → ProceduralAgent subclass + config dict (2 files, no prompt).

    Runs the base-class standard loop, then registers the generated agent inline in
    ``__call__`` once the loop finishes. The requested agent name comes from the task
    text; the agent writes files under the conventional ``extension/`` paths and reports
    those paths in its done_tool reasoning so the registration hook can locate them.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="agent_generate_agent")
    description: str = Field(
        default="An agent that generates a new agent Python class and optional HTML prompt from a description."
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
            prompt_name=prompt_name or "agent_generate_agent",
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )

    async def _finalize_run(self, response, ctx):
        """Run the base loop, then register the freshly generated agent.

        The registration hook locates the generated files by scanning the agent's
        final done_tool reasoning for their paths, so those paths MUST appear there.
        """
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent
        from autogenesis.sandbox.project import staged_extension_root

        # Register the generated agent (and prompt) now that the loop has finished.
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
                    "Registration failed; include the generated file path in the "
                    "done_tool reasoning."
                )
        return response
