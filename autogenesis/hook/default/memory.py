"""MemoryHook — feeds TraceEvents into the memory systems from agent lifecycle hooks.

Every agent calls ``memory_hook`` with the same envelope (event, agent_name,
task_id, use_memory, memory_name); the per-event payload is the rest. The dict
is validated into ``MemoryHookInput`` here, so the hook has one consistent,
typed contract regardless of which agent fired it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from autogenesis.hook.types import Hook, HookContext, HookEvent, HookResult
from autogenesis.registry import HOOK
from autogenesis.trace.types import (
    TraceEvent,
    TraceEventType,
    agent_start_event,
    agent_call_event,
    agent_end_event,
    tool_call_event,
    skill_call_event,
)


# Envelope keys — present on every call; everything else is the per-event payload.
_ENVELOPE_KEYS = {"event", "agent_name", "task_id", "use_memory", "memory_name"}


class MemoryHookInput(BaseModel):
    """Typed contract for every ``memory_hook`` call. Agents still pass a dict;
    it is validated into this model so missing fields get safe defaults."""
    model_config = ConfigDict(extra="allow")  # tolerate extra payload keys (e.g. todos/flow_steps)

    # —— Envelope (always present) ——
    event: HookEvent
    agent_name: str = ""
    task_id: Optional[str] = None
    use_memory: bool = True
    memory_name: str = "general_memory_system"

    # —— Lifecycle ——
    task: Optional[str] = None              # ON_START
    result: Optional[str] = None            # ON_STOP
    success: Optional[bool] = None

    # —— Step loop (sub-agents) ——
    step_number: Optional[int] = None
    reasoning: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    action_result: Optional[Any] = None
    error: Optional[str] = None

    # —— Orchestration (MetaAgent ON_CALL) ——
    note: Optional[Dict[str, Any]] = None           # {event, detail, status}
    subtask_event: Optional[Dict[str, Any]] = None  # {action, data}
    final_result: Optional[str] = None


@HOOK.register_module(force=True)
class MemoryHook(Hook):
    """Routes agent lifecycle TraceEvents into the per-session memory systems."""

    name: str = "memory_hook"
    description: str = "Feeds agent lifecycle events into memory systems."
    events: list = []
    priority: int = 5

    async def handle(self, ctx: HookContext) -> HookResult:
        """Validate the lifecycle payload and emit the resulting TraceEvent into memory.

        Coerces the raw ``ctx.input`` into a typed :class:`MemoryHookInput`,
        builds the corresponding :class:`TraceEvent`, and emits it into the
        session's primary memory system plus the ``file_system_memory`` sink.
        All failures are logged and swallowed so memory is best-effort and never
        blocks the agent.

        Args:
            ctx: Hook context whose ``id`` is the session id and whose ``input``
                is the memory-hook envelope plus per-event payload.

        Returns:
            Always ``HookResult.allow()`` (this hook only observes).
        """
        from autogenesis.memory import memory_manager
        from autogenesis.logger import logger

        try:
            inp = MemoryHookInput.model_validate(ctx.input or {})
        except Exception as e:
            logger.warning(f"| ⚠️ MemoryHook: invalid input ({e})")
            return HookResult.allow()

        if not inp.use_memory:
            return HookResult.allow()

        event = self._build_event(inp, ctx.id)
        if event is None:
            return HookResult.allow()

        # Primary memory
        try:
            info = await memory_manager.get_info(inp.memory_name)
            if info and info.instance is not None:
                await info.instance.emit(event, session_id=ctx.id)
        except Exception as e:
            logger.warning(f"| ⚠️ MemoryHook (primary) error on {inp.event}: {e}")

        # FileSystemMemory as secondary sink
        if inp.memory_name != "file_system_memory":
            try:
                fs = await memory_manager.get_info("file_system_memory")
                if fs and fs.instance is not None:
                    await fs.instance.emit(event, session_id=ctx.id)
            except Exception as e:
                logger.warning(f"| ⚠️ MemoryHook (file_system) error on {inp.event}: {e}")

        return HookResult.allow()

    def _build_event(self, inp: MemoryHookInput, session_id: str) -> TraceEvent | None:
        """Translate a validated lifecycle input into the matching TraceEvent.

        Maps ON_START/ON_STOP/POST_STEP/POST_ACTION to their event factories and
        packs MetaAgent ON_CALL orchestration payloads (note/subtask/result) into
        AGENT_CALL metadata.

        Returns:
            The built :class:`TraceEvent`, or ``None`` for events that carry no
            memory-relevant content.
        """
        task_id = inp.task_id or session_id

        if inp.event == HookEvent.ON_START:
            return agent_start_event(
                session_id=session_id, task_id=task_id,
                agent_name=inp.agent_name, task_content=inp.task,
            )

        if inp.event == HookEvent.ON_STOP:
            return agent_end_event(
                session_id=session_id, task_id=task_id, agent_name=inp.agent_name,
                success=not bool(inp.error), result=inp.result,
            )

        if inp.event == HookEvent.POST_STEP:
            return agent_call_event(
                session_id=session_id, task_id=task_id, agent_name=inp.agent_name,
                step_number=inp.step_number, reasoning=inp.reasoning,
            )

        if inp.event == HookEvent.POST_ACTION:
            action = inp.action or {}
            atype = action.get("type", "tool")
            factory = tool_call_event if atype == "tool" else skill_call_event
            return factory(
                session_id=session_id, task_id=task_id, agent_name=inp.agent_name,
                step_number=inp.step_number, action_index=action.get("index", 0),
                action_name=action.get("name", ""), result=inp.action_result,
                success=not bool(inp.error), duration_ms=None, error=inp.error,
                description=action.get("description") or None,
            )

        if inp.event == HookEvent.ON_CALL:
            # Orchestration payload (note / subtask_event / final_result / legacy extras)
            # becomes AGENT_CALL metadata; the memory systems apply it to todos/flow/result.
            metadata = {
                k: v for k, v in inp.model_dump(exclude_none=True).items()
                if k not in _ENVELOPE_KEYS
            }
            return TraceEvent(
                event_type=TraceEventType.AGENT_CALL,
                session_id=session_id, agent_name=inp.agent_name, metadata=metadata,
            )

        return None
