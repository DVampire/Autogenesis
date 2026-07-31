"""FileSystemMemory — per-session memory persisted as a self-contained HTML file.

Shares all structure (todos, flowchart, recent/working tiers, result) with
GeneralMemorySystem via TieredMemory; the only difference is the on-disk format
(HTML here, JSON there).
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List

from pydantic import Field

from autogenesis.memory.default.tiered import TieredMemory, FlowStep, _SessionState
from autogenesis.registry import MEMORY_SYSTEM
from autogenesis.visual import css_path


def _he(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_NODE_CSS = {
    "done": "node-done", "running": "node-running", "failed": "node-failed",
    "pending": "node-pending", "skipped": "node-skipped", "cancelled": "node-skipped",
}
_BADGE_CSS = {
    "done": "status-done", "running": "status-running", "failed": "status-failed",
    "pending": "status-pending", "skipped": "status-skipped", "cancelled": "status-cancelled",
}


def _badge(status: str) -> str:
    css = _BADGE_CSS.get(status, "status-pending")
    return (
        f'<span class="status-badge {css}">'
        f'<span class="status-dot"></span>{_he(status)}</span>'
    )


@MEMORY_SYSTEM.register_module(force=True)
class FileSystemMemory(TieredMemory):
    """Per-session memory (todos + flowchart + recent/working + result) persisted as HTML."""

    name: str = Field(default="file_system_memory")
    description: str = Field(default="Todos, flowchart, recent/working memory and result persisted as HTML.")
    version: str = Field(default="1.1.0")
    file_ext: str = Field(default="memory.html")
    prompt_readable: bool = Field(default=False)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, state: _SessionState) -> str:
        css_rel = os.path.relpath(css_path("memory.css"), start=os.path.dirname(state.file_path))
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="UTF-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f"  <title>Memory — {_he(state.session_id)}</title>",
            f'  <link rel="stylesheet" href="{_he(css_rel)}">',
            "</head>",
            "<body>",
            '<div class="memory-page">',
            self._render_header(state),
            self._render_todos(state),
            self._render_flowchart(state),
            self._render_history(state),
        ]
        if state.final_result is not None:
            parts.append(self._render_result(state))
        parts += ["</div>", "</body>", "</html>"]
        return "\n".join(parts)

    def _render_header(self, state: _SessionState) -> str:
        return (
            '<div class="mem-header">'
            '<div class="mem-label">Memory</div>'
            f'<p class="mem-task">{_he(state.task)}</p>'
            f'<code class="mem-session">{_he(state.session_id)}</code>'
            "</div>"
        )

    def _render_todos(self, state: _SessionState) -> str:
        lines = ['<div class="mem-section">', "<h2>Todo List</h2>"]
        if not state.todos:
            return "\n".join(lines + ['<p class="mem-empty">No tasks yet.</p>', "</div>"])
        lines += [
            '<table class="todo-table">',
            "<thead><tr><th>#</th><th>Agent</th><th>Status</th><th>Description</th></tr></thead><tbody>",
        ]
        for i, t in enumerate(state.todos, 1):
            agent_cell = (
                f'<code class="todo-agent">{_he(t.agent_name)}</code>'
                if t.agent_name else '<span class="mem-empty">—</span>'
            )
            lines.append(
                "<tr>"
                f'<td class="todo-num">{i}</td>'
                f"<td>{agent_cell}</td>"
                f"<td>{_badge(t.status)}</td>"
                f'<td class="todo-desc">{_he(t.description)}</td>'
                "</tr>"
            )
        lines += ["</tbody>", "</table>", "</div>"]
        return "\n".join(lines)

    def _render_flowchart(self, state: _SessionState) -> str:
        lines = ['<div class="mem-section">', "<h2>Flow Chart</h2>"]
        if not state.flow_steps:
            return "\n".join(lines + ['<p class="mem-empty">No flow steps yet.</p>', "</div>"])

        by_round: Dict[int, List[FlowStep]] = defaultdict(list)
        for s in state.flow_steps:
            by_round[s.round].append(s)

        lines.append('<div class="flow-chart">')
        first = True
        for rnum in sorted(by_round.keys()):
            if not first:
                lines.append('<div class="flow-connector"></div>')
            first = False
            steps = by_round[rnum]
            round_label = steps[0].round_label if steps and steps[0].round_label else f"Round {rnum}"
            lines.append(
                '<div class="flow-round-header">'
                f'<span class="flow-round-num">Round {rnum}</span>'
                f'<span class="flow-round-goal">{_he(round_label)}</span>'
                "</div>"
            )
            lines.append('<div class="flow-round">')
            for s in steps:
                node_css = _NODE_CSS.get(s.status, "node-pending")
                agents_html = " ".join(f"<code>{_he(a)}</code>" for a in s.agents) if s.agents else ""
                lines.append(
                    f'<div class="flow-node {node_css}">'
                    f'<span class="flow-step-num">{s.step}</span>'
                    '<div class="flow-step-body">'
                    + (f'<div class="flow-step-agent">{agents_html}</div>' if agents_html else "")
                    + f'<div class="flow-step-label">{_he(s.label)}</div>'
                    "</div>"
                    + _badge(s.status)
                    + "</div>"
                )
            lines.append("</div>")  # flow-round
        lines += ["</div>", "</div>"]  # flow-chart, mem-section
        return "\n".join(lines)

    def _render_history(self, state: _SessionState) -> str:
        """Execution History: Working Memory (compacted summaries) + Recent Steps timeline."""
        lines = ['<div class="mem-section">', "<h2>Execution History</h2>"]
        
        constraints = []
        recent = []
        for r in state.recent:
            text = r.as_line().lower()
            if "constraint" in text or "established" in text or "verified fact" in text:
                constraints.append(r)
            else:
                recent.append(r)
                
        recent = recent[-self.recent_fetch:]

        if not state.working and not constraints and not recent:
            return "\n".join(lines + ['<p class="mem-empty">No history yet.</p>', "</div>"])

        if state.working:
            lines.append('<details class="compact-summary">')
            lines.append("<summary>Working Memory</summary>")
            for s in list(state.working):
                lines.append(f'<pre class="compact-summary-body">{_he(s)}</pre>')
            lines.append("</details>")

        if constraints:
            lines.append("<h3>Confirmed constraints</h3>")
            lines.append('<div class="history-timeline">')
            for r in constraints:
                badge = f" {_badge(r.status)}" if r.status else ""
                detail = f'<div class="history-detail">{_he(r.detail)}</div>' if r.detail else ""
                lines.append(
                    '<div class="history-entry">'
                    f'<span class="history-ts">{_he(r.ts)}</span>'
                    '<span class="history-dot"></span>'
                    '<div class="history-body">'
                    f'<div class="history-event">{_he(r.event)}{badge}</div>'
                    + detail
                    + "</div></div>"
                )
            lines.append("</div>")

        if recent:
            lines.append("<h3>Recent Steps</h3>")
            lines.append('<div class="history-timeline">')
            for r in recent:
                badge = f" {_badge(r.status)}" if r.status else ""
                detail = f'<div class="history-detail">{_he(r.detail)}</div>' if r.detail else ""
                lines.append(
                    '<div class="history-entry">'
                    f'<span class="history-ts">{_he(r.ts)}</span>'
                    '<span class="history-dot"></span>'
                    '<div class="history-body">'
                    f'<div class="history-event">{_he(r.event)}{badge}</div>'
                    + detail
                    + "</div></div>"
                )
            lines.append("</div>")

        lines.append("</div>")
        return "\n".join(lines)

    def _render_result(self, state: _SessionState) -> str:
        extra = "" if state.result_success else " result-failed"
        tag_cls = "tag-success" if state.result_success else "tag-failed"
        tag_label = "Completed" if state.result_success else "Failed"
        return (
            f'<div class="mem-section result-section{extra}">'
            "<h2>Final Result</h2>"
            f'<span class="result-tag {tag_cls}">{tag_label}</span>'
            f"<pre>{_he(state.final_result)}</pre>"
            "</div>"
        )
