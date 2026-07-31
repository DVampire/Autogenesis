"""TraceEvent type hierarchy — every agent execution step produces one of these."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from autogenesis.utils import make_id


class TraceEventType(str, Enum):
    """Agent / tool / skill lifecycle events, plus error."""

    # Agent lifecycle
    AGENT_START = "agent_start"   # agent begins
    AGENT_CALL  = "agent_call"    # mid-execution step / state update
    AGENT_END   = "agent_end"     # agent finishes (success or failure)

    # Tool lifecycle
    TOOL_START  = "tool_start"
    TOOL_CALL   = "tool_call"     # tool result received
    TOOL_END    = "tool_end"

    # Skill lifecycle
    SKILL_START = "skill_start"
    SKILL_CALL  = "skill_call"    # skill result received
    SKILL_END   = "skill_end"

    # Deterministic orchestration lifecycle
    WORKFLOW_START = "workflow_start"
    WORKFLOW_NODE_START = "workflow_node_start"
    WORKFLOW_NODE_END = "workflow_node_end"
    WORKFLOW_FRAME_START = "workflow_frame_start"
    WORKFLOW_FRAME_END = "workflow_frame_end"
    WORKFLOW_END = "workflow_end"

    # Misc
    ERROR       = "error"
    CUSTOM      = "custom"


class EventProvenance(str, Enum):
    """Where this event originated."""
    LIVE        = "live"
    TEST        = "test"
    REPLAY      = "replay"
    HEALTHCHECK = "healthcheck"


class EventConfidence(str, Enum):
    """Confidence level — gates automated downstream actions."""
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class TraceEvent(BaseModel):
    """A single, immutable trace record produced during agent execution."""

    id: str = Field(default_factory=lambda: make_id())
    event_type: TraceEventType

    session_id:   Optional[str] = None
    task_id:      Optional[str] = None
    agent_name:   Optional[str] = None

    label: str = Field(default="")

    step_number:  Optional[int] = None
    action_index: Optional[int] = None
    action_type:  Optional[str] = None   # "tool" | "skill"
    action_name:  Optional[str] = None

    input:    Optional[Dict[str, Any]] = Field(default=None)
    output:   Optional[Any]            = Field(default=None)
    reasoning: Optional[str]           = Field(default=None)
    message:  Optional[str]            = Field(default=None)
    success:  Optional[bool]           = None
    error:    Optional[str]            = None

    duration_ms: Optional[float] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    seq_no:      Optional[int] = Field(default=None)
    fingerprint: Optional[str] = Field(default=None)
    provenance:  EventProvenance  = Field(default=EventProvenance.LIVE)
    confidence:  EventConfidence  = Field(default=EventConfidence.HIGH)

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d


def compute_event_fingerprint(event: TraceEvent) -> str:
    import hashlib
    parts = [
        event.event_type.value,
        event.session_id or "",
        str(event.step_number or ""),
        str(event.action_index or ""),
        event.action_name or "",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Event constructors
# ---------------------------------------------------------------------------

def agent_start_event(
    session_id: str, task_id: str, agent_name: str, task_content: str,
) -> TraceEvent:
    return TraceEvent(
        event_type=TraceEventType.AGENT_START,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        label=f"Agent start: {agent_name}",
        input={"task": task_content},
    )


def agent_call_event(
    session_id: str, task_id: str, agent_name: str,
    step_number: int,
    reasoning: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> TraceEvent:
    return TraceEvent(
        event_type=TraceEventType.AGENT_CALL,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        step_number=step_number,
        label=f"Step {step_number}",
        reasoning=reasoning,
        message=reasoning,
        success=True,
        duration_ms=duration_ms,
    )


def agent_end_event(
    session_id: str, task_id: str, agent_name: str,
    success: bool, result: Optional[str],
    duration_ms: Optional[float] = None, error: Optional[str] = None,
) -> TraceEvent:
    return TraceEvent(
        event_type=TraceEventType.AGENT_END,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        label=f"Agent end: {agent_name} ({'ok' if success else 'fail'})",
        output=result,
        message=str(result) if result is not None else None,
        success=success,
        error=error,
        duration_ms=duration_ms,
        metadata={"success": success},
    )


def tool_start_event(
    session_id: str, task_id: str, agent_name: str,
    step_number: int, action_index: int, action_name: str,
    action_args: Dict[str, Any],
) -> TraceEvent:
    return TraceEvent(
        event_type=TraceEventType.TOOL_START,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        step_number=step_number, action_index=action_index,
        action_type="tool", action_name=action_name,
        label=f"tool: {action_name}", input=action_args,
    )


def tool_call_event(
    session_id: str, task_id: str, agent_name: str,
    step_number: int, action_index: int, action_name: str,
    result: Any, success: bool,
    duration_ms: Optional[float] = None, error: Optional[str] = None,
    description: Optional[str] = None,
) -> TraceEvent:
    meta: Dict[str, Any] = {"success": success}
    if description:
        meta["description"] = description
    return TraceEvent(
        event_type=TraceEventType.TOOL_CALL,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        step_number=step_number, action_index=action_index,
        action_type="tool", action_name=action_name,
        label=f"{action_name} ({'ok' if success else 'fail'})",
        output=result,
        message=str(result) if result is not None else None,
        success=success,
        error=error,
        duration_ms=duration_ms,
        metadata=meta,
    )


def skill_start_event(
    session_id: str, task_id: str, agent_name: str,
    step_number: int, action_index: int, action_name: str,
    action_args: Dict[str, Any],
) -> TraceEvent:
    return TraceEvent(
        event_type=TraceEventType.SKILL_START,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        step_number=step_number, action_index=action_index,
        action_type="skill", action_name=action_name,
        label=f"skill: {action_name}", input=action_args,
    )


def skill_call_event(
    session_id: str, task_id: str, agent_name: str,
    step_number: int, action_index: int, action_name: str,
    result: Any, success: bool,
    duration_ms: Optional[float] = None, error: Optional[str] = None,
    description: Optional[str] = None,
) -> TraceEvent:
    meta: Dict[str, Any] = {"success": success}
    if description:
        meta["description"] = description
    return TraceEvent(
        event_type=TraceEventType.SKILL_CALL,
        session_id=session_id, task_id=task_id, agent_name=agent_name,
        step_number=step_number, action_index=action_index,
        action_type="skill", action_name=action_name,
        label=f"{action_name} ({'ok' if success else 'fail'})",
        output=result,
        message=str(result) if result is not None else None,
        success=success,
        error=error,
        duration_ms=duration_ms,
        metadata=meta,
    )
