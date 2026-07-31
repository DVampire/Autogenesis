"""RuntimeManager — spawn / send / ask / stop / invoke / list / shutdown.

The runtime manages **running** agent refs via a single registry:
    _refs: Dict[str, AgentRef]

Every agent gets one inbox (AgentRef._inbox).  Messages to any running agent
are routed by ref name.  The protocol layer looks up a parent's ref by
parent_session_id (= ref.name) — no separate session registry is needed.
This module also provides the general transport verbs protocols build on:
send / ask / suspend-resume (rendezvous) / publish-subscribe (fan-out).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from autogenesis.logger import logger
from autogenesis.utils import Singleton, make_id
from autogenesis.runtime.pump import _pump
from autogenesis.runtime.types import (
    AgentDeadError,
    AgentRef,
    AgentStatus,
    BaseMessage,
    StopMessage,
    TaskMessage,
)

if TYPE_CHECKING:
    from autogenesis.agent.types import Agent


class RuntimeManager(metaclass=Singleton):
    """Singleton holding all running AgentRefs."""

    def __init__(self) -> None:
        self._refs: Dict[str, AgentRef] = {}
        # Suspend/resume rendezvous channel: key → future. One coroutine suspends on a
        # key and blocks; another (elsewhere, e.g. a different agent) resumes it by key.
        self._pending: Dict[str, "asyncio.Future"] = {}
        # Pub-sub: topic → set of subscriber ref names. Fan-out publish delivers to each.
        self._topics: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Suspend / resume channel — a request-reply rendezvous across agents
    # ------------------------------------------------------------------
    # A general pause/resume primitive (think an HTTP request awaiting its response, or a
    # process blocked until signalled). The escalation protocol is one user: a blocked
    # sub-agent ``suspend``s on its task_id; its parent ``resume``s that key with guidance.

    async def suspend(self, key: str, *, timeout: Optional[float] = None) -> Any:
        """Block the caller until ``resume(key, value)`` is called (or timeout), and
        return that value. Registers a one-shot future under ``key``."""
        existing = self._pending.get(key)
        if existing is not None and not existing.done():
            raise ValueError(f"Suspend key collision: {key!r} already has a waiter")
        fut = asyncio.get_running_loop().create_future()
        self._pending[key] = fut
        try:
            if timeout is not None:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
            return await fut
        finally:
            self._pending.pop(key, None)

    def resume(self, key: str, value: Any) -> bool:
        """Resume whoever is suspended on ``key`` with ``value``. Returns whether someone
        was actually waiting (False = already resumed / timed out / never suspended)."""
        fut = self._pending.get(key)
        if fut is not None and not fut.done():
            fut.set_result(value)
            return True
        return False

    # ------------------------------------------------------------------
    # Pub-sub — fan-out a message to every running subscriber of a topic
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, ref: AgentRef) -> None:
        self._topics.setdefault(topic, set()).add(ref.name)

    def unsubscribe(self, topic: str, ref: AgentRef) -> None:
        subs = self._topics.get(topic)
        if subs:
            subs.discard(ref.name)
            if not subs:
                self._topics.pop(topic, None)

    async def publish(self, topic: str, msg: BaseMessage) -> int:
        """Deliver ``msg`` to every RUNNING subscriber of ``topic``. Returns the count sent
        (dropping any subscriber that is no longer running)."""
        sent = 0
        for name in list(self._topics.get(topic, set())):
            ref = self._refs.get(name)
            if ref is not None and ref.status == AgentStatus.RUNNING:
                await ref._inbox.put(msg)
                sent += 1
            else:
                self._topics[topic].discard(name)
        return sent

    # ------------------------------------------------------------------
    # Spawn / stop lifecycle
    # ------------------------------------------------------------------

    async def spawn(
        self,
        agent: "Agent",
        *,
        name: Optional[str] = None,
    ) -> AgentRef:
        """Start a pump for one agent instance and register the ref."""
        agent_name = getattr(agent, "name", agent.__class__.__name__)
        ref_name   = name or f"{agent_name}-{make_id()}"
        existing   = self._refs.get(ref_name)
        if existing is not None and existing.status == AgentStatus.RUNNING:
            raise ValueError(f"AgentRef name collision: {ref_name!r} is already RUNNING")

        ref = AgentRef(name=ref_name, agent_name=agent_name, status=AgentStatus.RUNNING)
        ref._pump_task = asyncio.create_task(_pump(agent, ref), name=f"pump-{ref_name}")

        self._refs[ref_name] = ref
        logger.info(f"| 🟢 Runtime spawned: {ref}")
        return ref

    async def stop(
        self,
        ref: AgentRef,
        *,
        drain: bool = True,
        timeout: Optional[float] = None,
        reason: str = "manual",
    ) -> None:
        """Stop the ref's pump."""
        if ref.status != AgentStatus.RUNNING:
            self._refs.pop(ref.name, None)
            return

        ref.status = AgentStatus.STOPPING
        try:
            if drain:
                await ref._inbox.put(StopMessage(reason=reason))
                if ref._pump_task is not None:
                    if timeout is not None:
                        try:
                            await asyncio.wait_for(asyncio.shield(ref._pump_task), timeout=timeout)
                        except asyncio.TimeoutError:
                            logger.warning(f"| ⏱ stop(drain) timeout: {ref.name} — cancelling pump")
                            ref._pump_task.cancel()
                            await asyncio.gather(ref._pump_task, return_exceptions=True)
                    else:
                        await ref._pump_task
            else:
                if ref._pump_task is not None and not ref._pump_task.done():
                    ref._pump_task.cancel()
                    await asyncio.gather(ref._pump_task, return_exceptions=True)
        finally:
            if ref.status != AgentStatus.DEAD:
                ref.status = AgentStatus.STOPPED
            self._refs.pop(ref.name, None)
            logger.info(f"| ⚫ Runtime stopped: {ref}")

    async def shutdown(self) -> None:
        """Stop every running ref."""
        for ref in list(self._refs.values()):
            await self.stop(ref, drain=False, reason="shutdown")

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send(self, ref: AgentRef, msg: BaseMessage) -> None:
        """Fire-and-forget into a ref's inbox."""
        if ref.status != AgentStatus.RUNNING:
            raise AgentDeadError(f"Cannot send to {ref}: not RUNNING")
        await ref._inbox.put(msg)

    async def ask(
        self,
        ref: AgentRef,
        msg: BaseMessage,
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send into a ref's inbox and await the reply."""
        if msg.reply_future is None:
            msg.reply_future = asyncio.get_running_loop().create_future()
        await self.send(ref, msg)
        if timeout is not None:
            # A caller timeout must not cancel the future owned by the agent. The
            # in-flight handler may still finish and set its result; cancelling the
            # shared future here would otherwise turn that normal completion into an
            # InvalidStateError and kill the long-lived pump.
            return await asyncio.wait_for(asyncio.shield(msg.reply_future), timeout=timeout)
        return await msg.reply_future

    async def invoke(
        self,
        agent: "Agent",
        *,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        **task_kwargs: Any,
    ) -> Any:
        """One-shot: spawn + ask(TaskMessage) + stop.  Returns agent's result."""
        ref = await self.spawn(agent, name=name)
        try:
            task = task_kwargs.pop("task", None)
            msg  = TaskMessage(task=task, kwargs=task_kwargs)
            return await self.ask(ref, msg, timeout=timeout)
        finally:
            await self.stop(ref, drain=False)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[AgentRef]:
        return self._refs.get(name)

    def list(self) -> List[AgentRef]:
        return list(self._refs.values())


runtime_manager = RuntimeManager()
