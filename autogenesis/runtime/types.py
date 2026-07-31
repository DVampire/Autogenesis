"""Runtime types: AgentRef, status enum, and message classes.

The runtime is a thin mailbox/pump layer on top of existing Agent instances.
- AgentRef is the only externally-visible handle to a running agent.
- Messages (TaskMessage / StopMessage) flow into ref._inbox; the pump loop
  in autogenesis.runtime.pump dispatches them to the underlying Agent._run method.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from autogenesis.utils import make_id


class AgentStatus(str, Enum):
    RUNNING  = "running"
    STOPPING = "stopping"
    STOPPED  = "stopped"
    DEAD     = "dead"


class AgentDeadError(RuntimeError):
    """Raised when sending to an AgentRef that is not RUNNING."""


class BaseMessage(BaseModel):
    """Base class for all runtime messages."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=make_id)
    reply_future: Optional[asyncio.Future] = Field(default=None, exclude=True)


class TaskMessage(BaseMessage):
    """Run one task on the agent (maps to Agent._run(task=..., **kwargs))."""

    task: Optional[str] = None
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class StopMessage(BaseMessage):
    """Graceful stop request: pump exits after this message."""

    reason: str = "manual"


class AgentRef(BaseModel):
    """Handle to one running agent inside the runtime."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name:       str
    agent_name: str
    status:     AgentStatus = AgentStatus.RUNNING

    _inbox:         asyncio.Queue            = PrivateAttr(default_factory=asyncio.Queue)
    _pump_task:     Optional[asyncio.Task]   = PrivateAttr(default=None)
    _pending_reply: Optional[asyncio.Future] = PrivateAttr(default=None)

    def __repr__(self) -> str:
        return f"AgentRef(name={self.name!r}, agent={self.agent_name!r}, status={self.status.value})"

    __str__ = __repr__


AgentRef.model_rebuild()
