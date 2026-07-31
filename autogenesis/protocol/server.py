"""ProtocolManager — the channels agents talk over, built on the runtime's transport verbs.

runtime = how messages move (send / ask / suspend-resume / publish); protocol = the SHAPE
of each conversation. One manager, grouped by channel; each channel is one of four patterns:

  gate  (suspend/resume) : escalation — a blocked sub-agent asks its parent, resumes on reply
  ask   (invoke / ask)   : delegation — run another agent and get its Response (meta→sub, meta1→meta2)
                           query      — ask a running agent for a status snapshot
  tell  (send)           : progress   — stream status to the parent
                           control    — cancel / pause / resume a running agent
  fan-out (publish)      : pubsub     — broadcast an event to a topic's subscribers

Add a new channel here only when a real interaction needs it — the runtime primitives are
general; this file is just their typed conversations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from autogenesis.logger import logger
from autogenesis.response.types import Response
from autogenesis.runtime import runtime_manager
from autogenesis.utils import Singleton, make_id
from autogenesis.protocol.types import EscalationMessage, MonitorProgressMessage, ControlMessage, QueryMessage

_ESCALATION_TIMEOUT_S = 300.0


class ProtocolManager(metaclass=Singleton):
    """One handle for every agent-to-agent channel (mirror of ``runtime_manager``)."""

    # ------------------------------------------------------------------
    # escalation — gate: a blocked sub-agent asks its parent (runtime.suspend/resume)
    # ------------------------------------------------------------------

    async def escalate(self, ctx: Any, *, reason: str, situation: str = "", suggestion: str = "") -> str:
        """Send end: post the escalation to the parent and block until it replies. Returns
        the guidance (or a graceful-stop instruction if there is no parent / it times out)."""
        # Lineage lives on the field for an AgentContext, or in ``extra`` once the context
        # has been converted (e.g. into a tool's ToolContext) — check both.
        extra = getattr(ctx, "extra", {}) or {}
        parent_session_id = getattr(ctx, "parent_session_id", None) or extra.get("parent_session_id")
        if not parent_session_id:
            return "No parent to escalate to (running standalone). Proceed on your own or stop gracefully."
        parent_ref = runtime_manager.get(parent_session_id)
        if parent_ref is None:
            return "Parent is no longer running. Proceed on your own or stop gracefully."

        task_id = getattr(ctx, "subtask_id", None) or extra.get("subtask_id") or getattr(ctx, "id", "")
        msg = EscalationMessage(
            task_id=task_id, agent_name=getattr(ctx, "name", "") or "", session_id=getattr(ctx, "id", "") or "",
            reason=reason, situation=situation, suggestion=suggestion,
        )
        logger.info(f"| 🆘 Escalation from {msg.agent_name} [{task_id}] → {parent_session_id}")
        try:
            await runtime_manager.send(parent_ref, msg)
            guidance = await runtime_manager.suspend(task_id, timeout=_ESCALATION_TIMEOUT_S)
        except Exception as e:
            logger.warning(f"| ⏰ Escalation [{task_id}] failed/timeout: {e}")
            return "Parent did not respond in time. Please stop the current subtask gracefully."
        logger.info(f"| 💬 Escalation reply for [{task_id}]: {guidance}")
        return guidance

    def reply(self, task_id: str, guidance: str) -> bool:
        """Reply end: resume the sub-agent suspended on ``task_id``. Returns whether one waited."""
        delivered = runtime_manager.resume(task_id, guidance)
        logger.info(f"| 💬 Reply → [{task_id}]" + ("" if delivered else " (no waiter)"))
        return delivered

    # ------------------------------------------------------------------
    # delegation — ask: run another agent and get its Response (runtime.invoke)
    # ------------------------------------------------------------------

    async def delegate(
        self, child: Any, task: str, *,
        files: Optional[List[str]] = None, target_name: Optional[str] = None,
        allowlists: Optional[Dict[str, Any]] = None, parent_ref: Any = None, workspace_root: Optional[str] = None,
    ) -> Response:
        """Run ``child`` on ``task`` as a sub-agent of the caller and return its Response.
        ``parent_ref`` links the child back for escalation; ``allowlists`` optionally
        restricts its capabilities; ``target_name`` anchors an evolution target."""
        import os
        from autogenesis.agent.types import AgentContext  # local: agent → protocol.server would cycle at import time

        if target_name:
            task = f"Target capability: {target_name}\n\n{task}"
        ctx = AgentContext(
            id=f"{getattr(child, 'name', 'agent')}-{make_id()}",
            parent_session_id=(parent_ref.name if parent_ref is not None else None),
        )
        if target_name:
            ctx.extra["target_name"] = target_name
        effective_allowlists = dict(allowlists or {})
        if hasattr(child, "_target_capability_allowlists"):
            for key, value in child._target_capability_allowlists(target_name).items():
                if effective_allowlists.get(key) is None:
                    effective_allowlists[key] = value
        for key, val in effective_allowlists.items():
            if val is not None:
                ctx.extra[key] = val
        existing = [f for f in (files or []) if os.path.exists(f)]
        return await runtime_manager.invoke(child, task=task, files=existing or None, ctx=ctx, parent_ref=parent_ref)

    # ------------------------------------------------------------------
    # progress — tell: stream status to the parent (runtime.send)
    # ------------------------------------------------------------------

    async def report(self, parent_ref: Any, msg: MonitorProgressMessage) -> None:
        """Post a progress update to the parent's inbox (fire-and-forget)."""
        if parent_ref is not None:
            await runtime_manager.send(parent_ref, msg)

    # ------------------------------------------------------------------
    # control — tell: cancel / pause / resume a running agent (runtime.send)
    # ------------------------------------------------------------------

    async def cancel(self, ref: Any, reason: str = "") -> None:
        """Ask a running agent to stop gracefully (concludes after its current action)."""
        await runtime_manager.send(ref, ControlMessage(action="cancel", reason=reason))

    async def pause(self, ref: Any) -> None:
        """Ask a running agent to stop advancing after its current round (until resumed)."""
        await runtime_manager.send(ref, ControlMessage(action="pause"))

    async def resume(self, ref: Any) -> None:
        """Let a paused agent continue."""
        await runtime_manager.send(ref, ControlMessage(action="resume"))

    # ------------------------------------------------------------------
    # query — ask: request a running agent's status snapshot (runtime.ask)
    # ------------------------------------------------------------------

    async def query(self, ref: Any, *, timeout: Optional[float] = 30.0) -> Dict[str, Any]:
        """Ask a running agent for its current status snapshot (step, done, result-so-far, …)."""
        return await runtime_manager.ask(ref, QueryMessage(), timeout=timeout)

    # ------------------------------------------------------------------
    # pubsub — fan-out: broadcast to a topic's subscribers (runtime.publish)
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, ref: Any) -> None:
        """Start receiving messages published to ``topic`` in ``ref``'s inbox."""
        runtime_manager.subscribe(topic, ref)

    def unsubscribe(self, topic: str, ref: Any) -> None:
        """Stop receiving ``topic``'s messages."""
        runtime_manager.unsubscribe(topic, ref)

    async def publish(self, topic: str, msg: Any) -> int:
        """Deliver ``msg`` to every running subscriber of ``topic``. Returns the fan-out count."""
        return await runtime_manager.publish(topic, msg)


protocol_manager = ProtocolManager()
