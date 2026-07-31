"""Message-pump loop driving one AgentRef.

The pump owns nothing — it drains ref._inbox and dispatches every message
to agent.handle(msg, ref).  On StopMessage it exits cleanly; on an
unhandled pump-level exception the ref is marked DEAD.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autogenesis.logger import logger
from autogenesis.runtime.types import AgentRef, AgentStatus, StopMessage

if TYPE_CHECKING:
    from autogenesis.agent.types import Agent


async def _pump(agent: "Agent", ref: AgentRef) -> None:
    """Drain ref._inbox and call agent.handle(msg, ref) until StopMessage or crash."""
    try:
        while True:
            msg = await ref._inbox.get()

            if isinstance(msg, StopMessage):
                logger.info(f"| 🛑 Runtime stop: {ref.name} (reason={msg.reason})")
                return

            await agent.handle(msg, ref)

    except asyncio.CancelledError:
        logger.info(f"| ✋ Runtime pump cancelled: {ref.name}")
        raise
    except Exception as exc:
        logger.error(f"| 💀 Runtime pump crashed: {ref.name}: {exc}", exc_info=True)
        ref.status = AgentStatus.DEAD
