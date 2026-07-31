"""Hook types — HookEvent, HookContext, HookResult, and Hook base class."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.message import Message
from autogenesis.session import BaseContext


class HookEvent(str, Enum):
    """Lifecycle events that middleware can intercept."""

    # Message pipeline — fires inside _get_messages before returning to agent
    PRE_MESSAGES = "pre_messages"

    # Action lifecycle — fires around each action in _think_and_act
    PRE_ACTION = "pre_action"
    POST_ACTION = "post_action"

    # Step lifecycle — fires around each full agent step
    PRE_STEP = "pre_step"
    POST_STEP = "post_step"

    # Agent lifecycle
    ON_START = "on_start"
    ON_STOP = "on_stop"       # agent is about to call done_tool
    ON_ESCALATE = "on_escalate"  # agent is blocked and requests Meta guidance
    ON_CALL = "on_call"


class HookContext(BaseContext):
    """Context passed into hook manager and individual hook handlers.

    ``input`` carries the event payload dict passed to ``hook_manager``.
    Hook handlers read event data via ``ctx.input.get("event")``, etc.
    ``extra`` carries arbitrary caller-supplied data; not read by the framework.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(description="Unique identifier for this hook invocation.")
    name: str = Field(description="Name of the hook that fired.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this hook context.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Event payload dict passed by the caller.")


class HookDecision(str, Enum):
    """What the middleware wants to happen next."""
    ALLOW = "allow"       # continue normally
    BLOCK = "block"       # stop this action / step
    MODIFY = "modify"     # use modified_messages / modified_action


class HookResult(BaseModel):
    """What a middleware handler returns."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    decision: HookDecision = Field(default=HookDecision.ALLOW)
    reason: Optional[str] = Field(default=None, description="Human-readable reason (for BLOCK).")

    # Modified data — only used when decision == MODIFY
    modified_messages: Optional[List[Message]] = Field(default=None)
    modified_action: Optional[Dict[str, Any]] = Field(default=None)

    # Extra context to inject into the next agent message (like Claude Code additionalContext)
    additional_context: Optional[str] = Field(default=None)

    # Generic text output for request/response-style hooks (e.g. compact returns its summary here).
    output: Optional[str] = Field(default=None)

    # Per-step resource-budget snapshot collected by the constraint hook on PRE_STEP
    # (list of ConstraintStatus dumps). The agent renders this into its prompt.
    constraint_status: Optional[List[Dict[str, Any]]] = Field(default=None)

    @classmethod
    def allow(cls) -> "HookResult":
        """Build a result that lets the lifecycle event proceed unchanged."""
        return cls(decision=HookDecision.ALLOW)

    @classmethod
    def block(cls, reason: str = "") -> "HookResult":
        """Build a result that stops the current action/step, with an optional reason."""
        return cls(decision=HookDecision.BLOCK, reason=reason)

    @classmethod
    def modify_messages(cls, messages: List[Message], additional_context: str = "") -> "HookResult":
        """Build a MODIFY result that replaces the prompt messages (and optionally injects extra context)."""
        return cls(
            decision=HookDecision.MODIFY,
            modified_messages=messages,
            additional_context=additional_context or None,
        )

    @classmethod
    def modify_action(cls, action: Dict[str, Any]) -> "HookResult":
        """Build a MODIFY result that replaces the pending action with ``action``."""
        return cls(decision=HookDecision.MODIFY, modified_action=action)


class ContractViolation(Exception):
    """Raised (in strict mode) when a hook's MODIFY result violates message invariants."""


_VALID_ROLES = {"user", "system", "assistant"}


def check_message_contract(messages: List[Message], *, mode: str = "warn", hook_name: str = "") -> None:
    """Validate a hook's ``modified_messages`` against basic invariants (contract-as-code).

    Borrowed from HarnessX's strict/warn contract. Catches a MODIFY hook that would
    corrupt the prompt — the failure mode for LLM-generated evolution hooks. Checks:
      * result is non-empty (a hook returning ``[]`` would blank the prompt),
      * every message has a valid role,
      * at most one system message, and if present it is at position 0.

    ``mode``: ``strict`` raises :class:`ContractViolation`; ``warn`` logs; ``off`` skips.
    """
    if mode == "off" or messages is None:
        return
    problems: List[str] = []
    if len(messages) == 0:
        problems.append("modified_messages is empty (would blank the prompt)")
    roles = [getattr(m, "role", None) for m in messages]
    bad = [r for r in roles if r not in _VALID_ROLES]
    if bad:
        problems.append(f"invalid message role(s): {bad}")
    sys_idx = [i for i, r in enumerate(roles) if r == "system"]
    if len(sys_idx) > 1:
        problems.append(f"more than one system message (at {sys_idx})")
    elif sys_idx and sys_idx[0] != 0:
        problems.append(f"system message not at position 0 (at {sys_idx[0]})")

    if not problems:
        return
    detail = f"Hook '{hook_name}' MODIFY contract violation: " + "; ".join(problems)
    if mode == "strict":
        raise ContractViolation(detail)
    from autogenesis.logger import logger
    logger.warning(f"| ⚠️ {detail}")


def _merge_results(results: List[HookResult]) -> HookResult:
    """Merge results from parallel middleware handlers.

    Most restrictive decision wins (BLOCK > MODIFY > ALLOW).
    All additional_context strings are concatenated.
    For MODIFY, the last non-None modified_messages / modified_action wins.
    """
    if not results:
        return HookResult.allow()

    final_decision = HookDecision.ALLOW
    final_reason = None
    final_messages = None
    final_action = None
    context_parts: List[str] = []

    for r in results:
        if r.decision == HookDecision.BLOCK:
            final_decision = HookDecision.BLOCK
            if r.reason:
                final_reason = r.reason
        elif r.decision == HookDecision.MODIFY and final_decision != HookDecision.BLOCK:
            final_decision = HookDecision.MODIFY
            if r.modified_messages is not None:
                final_messages = r.modified_messages
            if r.modified_action is not None:
                final_action = r.modified_action

        if r.additional_context:
            context_parts.append(r.additional_context)

    return HookResult(
        decision=final_decision,
        reason=final_reason,
        modified_messages=final_messages,
        modified_action=final_action,
        additional_context="\n\n".join(context_parts) if context_parts else None,
    )


class Hook(BaseModel):
    """Base class for all hook handlers."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Unique name for this hook.")
    description: str = Field(default="", description="What this hook does.")
    enabled: bool = Field(default=True)
    # Execution priority — lower number runs first.
    priority: int = Field(default=100)

    async def handle(self, ctx: HookContext) -> HookResult:
        """Override this method to implement hook logic."""
        return HookResult.allow()

    async def cleanup(self, session_id: str) -> None:
        """Called when a session ends (ON_STOP). Override to release per-session state."""
