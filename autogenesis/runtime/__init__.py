"""Agent runtime: mailbox + pump + lifecycle on top of registered Agent instances."""

import atexit

from autogenesis.logger import logger
from autogenesis.runtime.server import RuntimeManager, runtime_manager
from autogenesis.runtime.types import (
    AgentDeadError,
    AgentRef,
    AgentStatus,
    BaseMessage,
    StopMessage,
    TaskMessage,
)


def _atexit_warn_on_leak() -> None:
    leaks = runtime_manager.list()
    if leaks:
        names = ", ".join(r.name for r in leaks)
        logger.warning(
            f"| 🪦 runtime: process exiting with {len(leaks)} non-stopped ref(s): {names}"
        )


atexit.register(_atexit_warn_on_leak)


__all__ = [
    "runtime_manager",
    "RuntimeManager",
    "AgentRef",
    "AgentStatus",
    "AgentDeadError",
    "BaseMessage",
    "TaskMessage",
    "StopMessage",
]
