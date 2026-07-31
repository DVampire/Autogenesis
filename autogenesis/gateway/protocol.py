"""Wire models shared by stdio and WebSocket Gateway transports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PROTOCOL_VERSION = 1


class GatewayCommand(BaseModel):
    """A request sent by an interactive client."""

    model_config = ConfigDict(extra="forbid")

    id: str
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION


class GatewayError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class GatewayResponse(BaseModel):
    """The direct result of a GatewayCommand."""

    kind: Literal["response"] = "response"
    id: str
    ok: bool
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[GatewayError] = None
    protocol_version: int = PROTOCOL_VERSION


class GatewayEvent(BaseModel):
    """An ordered, replayable server event."""

    kind: Literal["event"] = "event"
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    #: Which line of dialogue this belongs to. A project holds several, and the
    #: Gateway broadcasts every event to every client, so without this a client
    #: cannot tell its own conversation's work from the one in the next tab.
    #: Absent on project-wide events (a session opening, capabilities changing).
    conversation_id: Optional[str] = None
    task_id: Optional[str] = None
    seq_no: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    protocol_version: int = PROTOCOL_VERSION


def error_response(command_id: str, code: str, message: str, **details: Any) -> GatewayResponse:
    return GatewayResponse(
        id=command_id,
        ok=False,
        error=GatewayError(code=code, message=message, details=details or None),
    )
