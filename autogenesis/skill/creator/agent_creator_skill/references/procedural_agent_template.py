"""TEMPLATE — a procedural agent (deterministic, code-driven; NO LLM loop).

Copy to `extension/agent/{name}.py`, rename the class, and implement the steps.
A procedural agent has NO HTML prompt — it does not reason step by step. Use it when
the task is a fixed pipeline (e.g. read → process → report) that you can express in
code and that calls tools directly. Implement ``run_procedure``; never override
``__call__``, because direct and delegated calls share the mailbox runtime.

If the task needs step-by-step reasoning / dynamic tool choice, use
`tool_calling_agent_template.py` instead.
"""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.registry import AGENT
from autogenesis.agent.types import AgentContext, ProceduralAgent
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger


@AGENT.register_module(force=True)
class MyProceduralAgent(ProceduralAgent):
    """A deterministic, code-driven agent with a fixed pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="my_procedural_agent")
    description: str = Field(default="What this procedure does and when to use it.")
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
        max_step: int = 30,
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
            prompt_name=prompt_name,  # a procedural agent has no HTML prompt
            memory_name=memory_name,
            max_actions=max_actions,
            max_step=max_step,
            review_steps=review_steps,
            enable_evolving=enable_evolving,
            **kwargs,
        )

    async def run_procedure(
        self,
        task: str,
        files: Optional[List[str]] = None,
        ctx: AgentContext = None,
        **kwargs,
    ) -> Response:
        """Deterministic pipeline executed by ProceduralAgent.on_start."""
        logger.info(f"| 🚀 Starting {self.name}: {task}")
        try:
            # Call tools directly via tool_manager, e.g.:
            #   from autogenesis.tool.server import tool_manager
            #   resp = await tool_manager(name="read_file_tool", input={"path": "..."}, ctx=ctx)
            data = await self._step_read(task, ctx)
            processed = await self._step_process(data, ctx)
            result = await self._step_report(processed, ctx)
            return Response(type=ResponseType.AGENT, success=True,
                            message=result, data={"result": result})
        except Exception as e:
            logger.error(f"| ❌ [{self.name}] Workflow failed: {e}")
            return Response(type=ResponseType.AGENT, success=False, message=str(e))

    async def _step_read(self, task: Optional[str], ctx: AgentContext) -> Any:
        raise NotImplementedError("Implement the read step.")

    async def _step_process(self, data: Any, ctx: AgentContext) -> Any:
        raise NotImplementedError("Implement the process step.")

    async def _step_report(self, processed: Any, ctx: AgentContext) -> str:
        raise NotImplementedError("Implement the report step; return the final string.")
