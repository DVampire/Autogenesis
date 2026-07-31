"""Protocol message types — the typed envelopes carried over the runtime's channels.

Each is a ``runtime.BaseMessage`` (so it flows through an agent's inbox and can carry a
reply_future). The conversation logic that sends/answers them lives in ``server.py``.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from autogenesis.runtime import BaseMessage


class EscalationMessage(BaseMessage):
    """gate — posted to the parent when a sub-agent blocks; the context it replies from."""

    task_id: str
    agent_name: str = ""
    session_id: str = ""
    reason: str = ""
    situation: str = ""
    suggestion: str = ""

    @property
    def text(self) -> str:
        body = f"Reason: {self.reason}\nSituation: {self.situation}"
        if self.suggestion:
            body += f"\nSuggestion: {self.suggestion}"
        return body


class MonitorProgressMessage(BaseMessage):
    """tell — a periodic progress update about a running subprocess / sub-agent."""

    task_id: str
    agent_name: str = ""
    session_id: str = ""
    pid: int = 0
    status: Literal["running", "completed", "failed", "timeout"] = "running"
    elapsed: float = 0.0
    recent_output: str = ""
    exit_code: Optional[int] = None


class ControlMessage(BaseMessage):
    """tell — a cancel / pause / resume instruction to a running agent."""

    action: Literal["cancel", "pause", "resume"]
    reason: str = ""


class QueryMessage(BaseMessage):
    """ask — a request for a running agent's status snapshot (empty ``fields`` = full)."""

    fields: Optional[List[str]] = None
