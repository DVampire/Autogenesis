"""Task types for the Autogenesis task system.

Defines the core `Task` unit of work that gets submitted to the `AgentBus`,
along with supporting enums for status and priority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from autogenesis.utils import make_id


class TaskStatus(str, Enum):
    """Lifecycle states for a Task."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubTaskCategory(str, Enum):
    """Category of a subtask within MetaAgent's plan.

    ACTOR subtasks directly serve the user's goal — MetaAgent waits for all
    of them before returning a final answer.
    EVALUATOR, OPTIMIZER, and GENERATOR subtasks are system self-improvement
    work and do not block the user result.
    """

    ACTOR     = "actor"
    EVALUATOR = "evaluator"
    OPTIMIZER = "optimizer"
    GENERATOR = "generator"


class TaskPriority(int, Enum):
    """Priority levels for task scheduling.

    Higher numeric value → higher priority.
    """

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class Task(BaseModel):
    """Central unit of work submitted to the AgentBus.

    A Task is the top-level envelope for user intent.  The bus wraps it
    in a `BusMessage` and routes it through the planner ↔ sub-agent loop.
    The `session_id` field binds the task to a specific session so that
    concurrent tasks remain fully isolated from one another.
    """

    id: str = Field(
        default_factory=lambda: make_id(),
        description="Unique identifier for this task.",
    )
    content: str = Field(description="Natural-language description of what needs to be done.")
    files: List[str] = Field(
        default_factory=list,
        description="Optional list of file paths attached to the task.",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL,
        description="Scheduling priority; higher value processed first.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current lifecycle state of the task.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session this task is bound to.  When set, the bus routes the task "
            "through the session-isolated worker for that session_id, ensuring "
            "memory, todo lists, and working directory do not bleed across tasks."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs for caller-specific context.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the task was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the last status change.",
    )

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.updated_at = datetime.now(timezone.utc)

    def mark_done(self) -> None:
        self.status = TaskStatus.DONE
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self) -> None:
        self.status = TaskStatus.FAILED
        self.updated_at = datetime.now(timezone.utc)

    def mark_cancelled(self) -> None:
        self.status = TaskStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)
