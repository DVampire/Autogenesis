"""Escalate tool — a blocked sub-agent asks its parent MetaAgent for guidance.

This is the *send* side of the escalation channel: the tool calls
``protocol_manager.escalate``, which posts to the parent's inbox and suspends this
sub-agent until the parent replies (via ``reply_tool`` → ``protocol_manager.reply``).

Only meaningful for a sub-agent dispatched by a parent (it needs one to ask). Run
standalone, it reports that there is no parent to escalate to.
"""

from typing import Any, Dict

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Ask the parent MetaAgent for guidance when blocked, then continue with its reply."

_INSTRUCTION = """
## Function
Escalate to the parent MetaAgent when you are blocked and cannot proceed on your own, and get back concrete guidance. Use it instead of failing silently or guessing when: a capability you need is missing, the task is ambiguous or under-specified, you hit a blocker outside your scope, or you've failed the same way twice.

## Parameters
- reason (str, required): one line — why you are blocked / what you need.
- situation (str, optional): what you tried and what happened (evidence).
- suggestion (str, optional): what you think should happen (e.g. "a deploy tool needs to be generated").

## Guidance
- Only works when you were dispatched by a MetaAgent (there must be a parent to ask); otherwise it returns that there is no parent.
- The call blocks until the MetaAgent replies (or a timeout). Treat the returned guidance as an instruction and act on it; if told to stop, stop gracefully.
- Escalate sparingly — only for real blockers, not routine decisions you can make yourself.

## Example
{"name": "escalate_tool", "args": {"reason": "Need to deploy the site but no deploy capability is available", "situation": "Built the static site at /work/site but there is no tool to serve it at a URL", "suggestion": "Generate or enable a deployment tool"}}
"""


@TOOL.register_module(force=True)
class EscalateTool(Tool):
    """Ask the parent MetaAgent for guidance when blocked (fires the escalation protocol)."""

    name: str = "escalate_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="read_only", description="Only asks the parent for guidance; mutates nothing.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, reason: str, situation: str = "", suggestion: str = "", **kwargs) -> Response:
        from autogenesis.protocol import protocol_manager
        ctx = kwargs.get("ctx")
        try:
            guidance = await protocol_manager.escalate(ctx, reason=reason, situation=situation, suggestion=suggestion)
            return Response(type=ResponseType.TOOL, success=True, message=guidance)
        except Exception as e:
            logger.error(f"| ❌ escalate_tool failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Escalation failed: {e}")
