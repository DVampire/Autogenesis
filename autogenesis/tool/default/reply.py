"""reply tool — an orchestrator answers a sub-agent that ESCALATED.

The *reply* side of the escalation channel, the mirror of ``escalate_tool``: the sub-agent's
``escalate_tool`` calls ``protocol_manager.escalate`` (which suspends it); the parent's
``reply_tool`` calls ``protocol_manager.reply`` (which resumes it) with concrete guidance.
The pause/resume rendezvous is the runtime's suspend/resume channel, keyed by the
sub-agent's task_id — see ``autogenesis/protocol/server.py``.
"""

from typing import Any, Dict

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Reply to a sub-agent that ESCALATED (is blocked), unblocking it with concrete guidance."

_INSTRUCTION = """
## Function
Answer a sub-agent that escalated (reported it is blocked) so it can continue. Use it whenever an ESCALATE event is pending: give a concrete, actionable instruction, or tell the sub-agent to stop gracefully.

## Parameters
- task_id (str, required): the exact task_id from the ESCALATE event.
- reply (str, required): concrete guidance for the blocked sub-agent (or an instruction to stop gracefully).

## Guidance
- Reply promptly — the sub-agent is blocked, waiting, and holding up its round until you answer.
- Be specific: point at the capability/file/approach to use, or state the decision it was unsure about.

## Example
{"name": "reply_tool", "args": {"task_id": "subtask-1a2b3c", "reply": "Use write_file_tool to create the config at /work/app/config.json, then re-run the build."}}
"""


@TOOL.register_module(force=True)
class ReplyTool(Tool):
    """Reply to a blocked, escalated sub-agent (fires the reply side of the escalation protocol)."""

    name: str = "reply_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="read_only", description="Only unblocks a sub-agent; mutates nothing.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, task_id: str, reply: str, **kwargs) -> Response:
        from autogenesis.protocol import protocol_manager
        try:
            delivered = protocol_manager.reply(task_id, reply)
            msg = (f"Guidance delivered to sub-agent [{task_id}]." if delivered
                   else f"No sub-agent was waiting for [{task_id}] (already replied or timed out).")
            return Response(type=ResponseType.TOOL, success=True, message=msg)
        except Exception as e:
            logger.error(f"| ❌ reply_tool failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Reply failed: {e}")
