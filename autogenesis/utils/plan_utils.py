"""Generic markdown plan-file utilities.

Shared by PlanningAgent and DeepAnalyzerV3Agent (and any future agent that
needs a structured execution log written to disk).

Sections
--------
  TodoList        — checkbox step list with priority / status
  FlowChart       — mermaid LR diagram
  ExecutionHistory— append-only log of typed entries; each agent defines its
                    own entry dataclass and passes it to add_entry()
  FinalResult     — ## Final Result footer
  PlanFile        — orchestrates the four sections and owns disk I/O
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Protocol, TypeVar

from pydantic import BaseModel, Field
from autogenesis.utils.name_utils import make_id


# ---------------------------------------------------------------------------
# Plan path helper
# ---------------------------------------------------------------------------

def make_plan_path(workspace_root: str, session_id: str, suffix: str = "plan") -> str:
    """Generate a unique plan file path: {workspace_root}/{session_id}_{timestamp}_{random}.{suffix}.md"""
    unique_id = make_id()
    return os.path.join(workspace_root, f"{session_id}_{unique_id}.{suffix}.md")

# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# TodoList
# ---------------------------------------------------------------------------

class TodoStep(BaseModel):
    """One item in the todo list."""
    id: str
    description: str = ""
    agent_name: str = ""
    status: str = "pending"       # pending | done | skipped
    priority: str = "medium"      # high | medium | low
    round_number: int = 1
    result: Optional[str] = None


class TodoList:
    """## Todo List section.

    Usage (simple — no agent/priority):
        todo.set_steps(["Analyze X", "Verify Y"])
        todo.complete_step(round_number=1, result="done")

    Usage (full — with agent/priority, as in PlanningAgent):
        todo.add_steps([TodoStep(id=..., agent_name=..., priority=..., round_number=...)])
        todo.complete_round(round_number=1, summaries=[...])
    """

    _PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    def __init__(self, task: str) -> None:
        self.task = task
        self._steps: List[TodoStep] = []
        self._idx: int = 0

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_steps(self, steps: List[str], priority: str = "medium") -> None:
        """Replace the step list with simple string descriptions."""
        self._steps = []
        self._idx = 0
        for desc in steps:
            self._idx += 1
            self._steps.append(TodoStep(
                id=f"step-{self._idx}",
                description=desc,
                priority=priority,
                round_number=1,
            ))

    def add_steps(self, steps: List[TodoStep]) -> None:
        """Append fully-specified steps (planning agent style)."""
        for s in steps:
            self._idx += 1
            if not s.id:
                s.id = f"step-{self._idx}"
            self._steps.append(s)

    def complete_step(self, result: str = "") -> None:
        """Mark the first pending step as done."""
        for s in self._steps:
            if s.status == "pending":
                s.status = "done"
                s.result = result or None
                break

    def complete_round(self, round_number: int, summaries: Optional[List[str]] = None) -> None:
        """Mark ALL pending steps in this round as done (planning agent style)."""
        pending = [s for s in self._steps if s.round_number == round_number and s.status == "pending"]
        for i, step in enumerate(pending):
            step.status = "done"
            if summaries and i < len(summaries) and summaries[i]:
                step.result = summaries[i]

    def skip_pending(self) -> None:
        for s in self._steps:
            if s.status == "pending":
                s.status = "skipped"

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> str:
        lines = [f"Task: {self.task}\n\n## Todo List\n"]
        if not self._steps:
            lines.append("*(no steps planned yet)*")
            return "\n".join(lines)

        by_round: Dict[int, List[TodoStep]] = defaultdict(list)
        for s in self._steps:
            by_round[s.round_number].append(s)

        for rnum in sorted(by_round.keys()):
            group = by_round[rnum]
            concurrent = len(group) > 1
            label = f"Round {rnum}" + (" (concurrent)" if concurrent else "")
            lines.append(f"**{label}**")
            for s in group:
                cb = "[x]" if s.status == "done" else ("[~]" if s.status == "skipped" else "[ ]")
                emoji = self._PRIORITY_EMOJI.get(s.priority, "🟡")
                display = f"{s.agent_name}: {s.description}" if s.agent_name else s.description
                lines.append(f"- {cb} **{s.id}** {emoji} {display}")
                if s.result:
                    lines.append(f"  > {s.result}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# FlowChart
# ---------------------------------------------------------------------------

class FlowChartStep(BaseModel):
    """One node in the flowchart."""
    number: int
    agents: List[str] = Field(default_factory=list)
    label: str = ""
    is_planned: bool = False


class FlowChart:
    """## Execution Flow mermaid diagram.

    Usage (simple — linear steps, as in DeepAnalyzerV3):
        chart.set_steps(["Analyze X", "Verify Y"])
        chart.finalize("done")

    Usage (full — with concurrent agents, as in PlanningAgent):
        chart.add_step(FlowChartStep(number=1, agents=["a", "b"], is_planned=False))
        chart.finalize("done")
    """

    def __init__(self, task: str) -> None:
        self.task = task
        self._steps: List[FlowChartStep] = []
        self._status: str = "running"

    @staticmethod
    def _safe(t: str) -> str:
        return t.replace('"', "'").replace('[', '(').replace(']', ')')

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_steps(self, steps: List[str]) -> None:
        """Replace with a linear list of step descriptions."""
        self._steps = [
            FlowChartStep(number=i, label=desc)
            for i, desc in enumerate(steps, 1)
        ]

    def add_step(self, step: FlowChartStep) -> None:
        """Append or update a step (planning agent style)."""
        for existing in self._steps:
            if existing.number == step.number:
                existing.agents = step.agents
                existing.label = step.label
                existing.is_planned = step.is_planned
                return
        self._steps.append(step)

    def finalize(self, status: str) -> None:
        self._status = status

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _node(self, node_id: str, label: str, is_planned: bool) -> str:
        safe = self._safe(label)
        return f'    {node_id}(["{safe}"])' if is_planned else f'    {node_id}["{safe}"]'

    def render(self) -> str:
        lines = ["## Execution Flow\n", "```mermaid", "graph LR"]
        lines.append("  subgraph execution [Execution Flow]")

        if not self._steps:
            lines.append(f'    start(["{self._safe(self.task)}"])')
            if self._status in ("done", "failed"):
                tag = "Done" if self._status == "done" else "Failed"
                lines.append(f'    start --> finish(["{tag}"])')
            lines.append("  end")
            lines.append("```")
            return "\n".join(lines)

        task_idx = 0
        prev_nodes: List[str] = []

        for s in self._steps:
            agents = s.agents if s.agents else ([s.label] if s.label else [f"Step {s.number}"])
            planned = s.is_planned

            if len(agents) == 1:
                task_idx += 1
                nid = f"s{task_idx}"
                lines.append(self._node(nid, f"Step {task_idx}: {agents[0]}", planned))
                for prev in prev_nodes:
                    lines.append(f"    {prev} --> {nid}")
                prev_nodes = [nid]
            else:
                fork_id = f"fork_r{s.number}"
                join_id = f"join_r{s.number}"
                lines.append(f"    {fork_id}(( ))")
                lines.append(f"    {join_id}(( ))")
                for prev in prev_nodes:
                    lines.append(f"    {prev} --> {fork_id}")
                for agent in agents:
                    task_idx += 1
                    nid = f"s{task_idx}"
                    lines.append(self._node(nid, f"Step {task_idx}: {agent}", planned))
                    lines.append(f"    {fork_id} --> {nid}")
                    lines.append(f"    {nid} --> {join_id}")
                prev_nodes = [join_id]

        if self._status in ("done", "failed") and prev_nodes:
            tag = "Done" if self._status == "done" else "Failed"
            lines.append(f'    finish(["{tag}"])')
            for prev in prev_nodes:
                lines.append(f"    {prev} --> finish")

        lines.append("  end")
        lines.append("```")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ExecutionHistory — generic, entry type is defined by the caller
# ---------------------------------------------------------------------------

class EntryRenderable(Protocol):
    """Any entry passed to ExecutionHistory must implement render() -> List[str]."""
    def render(self) -> List[str]: ...


E = TypeVar("E")


class ExecutionHistory(Generic[E]):
    """## Execution Log section — generic over entry type.

    Each agent defines its own entry dataclass with a render() -> List[str] method
    and calls add_entry(entry).
    """

    def __init__(self) -> None:
        self._entries: List[Any] = []

    def add_entry(self, entry: Any) -> None:
        self._entries.append(entry)

    def last_entry(self) -> Optional[Any]:
        return self._entries[-1] if self._entries else None

    def render(self) -> str:
        lines = ["## Execution Log\n"]
        if not self._entries:
            lines.append("*(no steps yet)*")
            return "\n".join(lines)
        for entry in self._entries:
            lines.extend(entry.render())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# FinalResult
# ---------------------------------------------------------------------------

class FinalResult:
    """## Final Result section."""

    def __init__(self) -> None:
        self._answer: Optional[str] = None
        self._reasoning: Optional[str] = None
        self._success: Optional[bool] = None

    def finalize(self, answer: str, success: bool, reasoning: Optional[str] = None) -> None:
        self._answer = answer
        self._reasoning = reasoning
        self._success = success

    @property
    def is_set(self) -> bool:
        return self._answer is not None

    @property
    def success(self) -> Optional[bool]:
        return self._success

    @property
    def value(self) -> Optional[str]:
        return self._answer

    @property
    def reasoning(self) -> Optional[str]:
        return self._reasoning

    def render(self) -> str:
        if self._answer is None:
            return ""
        tag = "Completed" if self._success else "Failed"
        parts = [f"## Final Result — {tag}"]
        if self._reasoning:
            parts.append(f"\n### Reasoning\n\n{self._reasoning}")
        parts.append(f"\n### Answer\n\n{self._answer}\n")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# PlanFile — orchestrates the four sections and owns disk I/O
# ---------------------------------------------------------------------------

class PlanFile:
    """Manages a single markdown execution log file.

    Parameters
    ----------
    path : str
        Absolute path to the .md file.
    task : str
        The task description — shown in the Todo List header.
    session_id : str, optional
        Session identifier (used by PlanningAgent for keying; ignored otherwise).
    """

    def __init__(self, path: str, task: str, session_id: str = "") -> None:
        self.path = path
        self.task = task
        self.session_id = session_id

        self.todo_list:    TodoList           = TodoList(task=task)
        self.flow_chart:   FlowChart          = FlowChart(task=task)
        self.exec_history: ExecutionHistory   = ExecutionHistory()
        self.final_result: FinalResult        = FinalResult()

    def finalize(self, answer: str, success: bool, reasoning: Optional[str] = None) -> None:
        self.todo_list.skip_pending()
        self.final_result.finalize(answer=answer, success=success, reasoning=reasoning)
        self.flow_chart.finalize("done" if success else "failed")

    def render(self) -> str:
        parts = [
            self.todo_list.render(),
            "",
            self.flow_chart.render(),
            "",
            self.exec_history.render(),
        ]
        final = self.final_result.render()
        if final:
            parts.append(final)
        return "\n".join(parts)

    async def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        content = self.render()
        await asyncio.to_thread(self._write_sync, content)

    def _write_sync(self, content: str) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(content)
