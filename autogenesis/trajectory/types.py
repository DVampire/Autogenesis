"""Trajectory types — step-level execution records for SFT / RL training data.

A ``Trajectory`` is a step-aggregated, reward-annotated view of one agent run,
formalized as a sequence of steps ``s_t = (z_t, a_t, o_t, r_t)``:

    z_t  messages_sent   the effective prompt actually sent to the model this step
    a_t  reasoning + actions   the assistant's structured think-and-act output
    o_t  observations     each action's result / error
    r_t  reward           task-level reward, backfilled at finalize

Unlike ``TraceEvent`` (a raw, immutable event log for observability), a
Trajectory is the *trainable* projection: ``to_sft_records()`` emits one
OpenAI-chat record per step, ``to_rl_records(fmt)`` delegates to a
framework-specific :class:`RLFormat` (e.g. VERL).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.session import BaseContext


class TrajectoryContext(BaseContext):
    """Context identifying one agent run's trajectory (parallel to HookContext).

    ``id`` is the session id (``ctx.id``); ``task_id`` is the specific run
    within that session; ``input`` carries the per-event payload (messages,
    action, result, tokens, …) that the manager reads at each lifecycle point.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    task_id: str = Field(description="Run identifier this trajectory belongs to.")
    agent_name: str = Field(default="", description="Name of the agent being recorded.")

    @property
    def session_id(self) -> str:
        return self.id


def _message_to_dict(msg: Any) -> Dict[str, Any]:
    """Serialize a Message (or already-plain dict) to a JSON-safe chat dict.

    Messages flowing through hooks are ``src.message`` pydantic objects; be
    tolerant of plain dicts too so the trajectory never crashes on odd input.
    """
    if isinstance(msg, dict):
        return msg
    role = getattr(msg, "role", "user")
    # Message subclasses expose a ``.text`` convenience property.
    content = getattr(msg, "text", None)
    if content is None:
        content = getattr(msg, "content", "")
    out: Dict[str, Any] = {"role": role, "content": content if isinstance(content, str) else str(content)}
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]
    return out


class TrajectoryStep(BaseModel):
    """One think-and-act step: prompt in, structured decision + observations out."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_number: int
    # z_t — the effective context actually sent to the model this step.
    # Kept as Any (not List[Message]) to avoid pydantic re-validation
    # downcasting HumanMessage/SystemMessage subclasses to the base Message.
    messages_sent: List[Any] = Field(default_factory=list)
    # a_t — the assistant's structured output.
    reasoning: str = ""
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    # o_t — one entry per executed action.
    observations: List[Dict[str, Any]] = Field(default_factory=list)
    token_usage: int = 0
    # r_t — backfilled from the task-level reward at finalize.
    reward: float = 0.0

    def _assistant_message(self) -> Dict[str, Any]:
        """The assistant's trainable target as a NATIVE tool-calling turn.

        Native mode: the model emits reasoning (thinking/text) plus native
        ``tool_calls``. We project that to the OpenAI-chat assistant shape —
        ``content`` = reasoning, ``tool_calls`` = one function call per action
        (``arguments`` kept as a JSON string, ``name`` the tool name the model
        actually emitted — the entity's own registered name, e.g. ``bash_tool``)
        — so the SFT/RL target is byte-faithful to what the model produces at
        inference. Training on any other shape would teach a different output
        schema than the agent uses.
        """
        tool_calls: List[Dict[str, Any]] = []
        for i, a in enumerate(self.actions):
            args = a.get("args", "")
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
            tool_calls.append({
                "id": a.get("id") or f"call_{i}",
                "type": "function",
                "function": {"name": a.get("name", ""), "arguments": args},
            })
        msg: Dict[str, Any] = {"role": "assistant", "content": self.reasoning}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg

    def to_sft_record(self) -> Dict[str, Any]:
        """One OpenAI-chat SFT record: prompt messages + assistant target + reward.

        The assistant target is a native tool-calling turn (``content`` +
        ``tool_calls``), matching what the agent emits at inference.
        """
        messages = [_message_to_dict(m) for m in self.messages_sent]
        messages.append(self._assistant_message())
        return {"messages": messages, "reward": self.reward, "step": self.step_number}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "messages_sent": [_message_to_dict(m) for m in self.messages_sent],
            "reasoning": self.reasoning,
            "actions": self.actions,
            "observations": self.observations,
            "token_usage": self.token_usage,
            "reward": self.reward,
        }


class Trajectory(BaseModel):
    """A reward-annotated, step-aggregated record of one agent run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    task_id: str
    agent_name: str = ""
    task_description: str = ""
    steps: List[TrajectoryStep] = Field(default_factory=list)
    success: bool = False
    final_result: Optional[str] = None
    reward: float = 0.0
    # Multi-agent causal links: sub-agent task_ids spawned during this run.
    subtask_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def backfill_reward(self, reward: float) -> None:
        """Propagate a task-level reward to the trajectory and every step."""
        self.reward = reward
        for step in self.steps:
            step.reward = reward

    def to_sft_records(self) -> List[Dict[str, Any]]:
        """One SFT record per step (OpenAI chat format + reward)."""
        return [step.to_sft_record() for step in self.steps]

    def to_rl_records(self, fmt: "RLFormat") -> List[Dict[str, Any]]:
        """Delegate to a framework-specific RL format (e.g. VERL)."""
        return fmt.to_episode(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "task_description": self.task_description,
            "success": self.success,
            "final_result": self.final_result,
            "reward": self.reward,
            "subtask_ids": self.subtask_ids,
            "metadata": self.metadata,
            "steps": [s.to_dict() for s in self.steps],
        }


@runtime_checkable
class RLFormat(Protocol):
    """Framework-specific RL episode serializer.

    Concrete formats (VERL, SGLang/slime, …) live in ``autogenesis/trajectory/default/``
    so the core stays free of training-framework imports.
    """

    name: str

    def to_episode(self, trajectory: Trajectory) -> List[Dict[str, Any]]:
        ...


__all__ = ["TrajectoryContext", "TrajectoryStep", "Trajectory", "RLFormat"]
