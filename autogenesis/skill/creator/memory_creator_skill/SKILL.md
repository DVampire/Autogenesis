---
name: memory_creator_skill
description: Create new memory systems, improve/optimize existing ones, and evaluate memory quality — the full memory lifecycle in this framework. Use whenever the task involves authoring a new memory system (a Python class that accumulates a session's events and renders them back for prompt injection), editing/improving an existing one, or evaluating/scoring one. MetaAgent uses it to orchestrate the create->evaluate->improve loop across sub-agents.
version: 1.0.0
type: [orchestrator, worker]
category: meta
requirements: [cpu]
metadata: {}
---

# Memory Creator

A single skill for the full lifecycle of **memory systems**: creating, improving, and evaluating them. A memory system decides **what an agent still knows** on its next step: it consumes the session's event stream and renders a bounded view of it back into the prompt. Everything the agent has done that is not rendered is, in effect, forgotten.

## How this skill is used — four roles, one body of knowledge

- **MetaAgent (orchestrator role)** — drives the create->evaluate->improve loop. See **Orchestration**.
- **memory_generate_agent** — reads **Creating a memory system**.
- **memory_optimize_agent** — reads **Improving a memory system**.
- **memory_evaluate_agent** — reads **Evaluating a memory system**.

The sub-agents are headless: each runs one phase autonomously and returns a result.

## Framework conventions (read once)

A memory system is a **single Python file** (like a tool, unlike an environment):
```
{extension_root}/memory/{name}.py
```
**Registration is automatic via a hook**: after writing the file, include its path in your `done_tool` reasoning — the `memory_registration_hook` registers it.

### The Python class

Subclass `TieredMemory` and override how the accumulated state is rendered. The base
class already handles event ingestion (`emit`) and retrieval (`get`); what a new
memory system contributes is **selection and presentation** — which of the session's
records survive into the next prompt, and in what shape.

```python
from typing import Any
from pydantic import Field

from autogenesis.memory.default.tiered import TieredMemory, _SessionState
from autogenesis.registry import MEMORY_SYSTEM


@MEMORY_SYSTEM.register_module(force=True)
class MyMemory(TieredMemory):
    """One-line purpose — becomes the description if none is given."""

    name: str = Field(default="my_memory")
    description: str = Field(default="What this memory keeps and why.")
    enable_evolving: bool = Field(default=True)

    def _render(self, state: _SessionState) -> str:
        """Return the text injected into the agent's next prompt."""
        return "\n".join(r.as_line() for r in state.recent)
```

- `name` must match the file stem (`my_memory.py` → `my_memory`).
- `enable_evolving: bool = Field(default=True)` — required, or the component cannot be optimized later.
- Keep `_render` **bounded**: an unbounded transcript defeats the purpose and will blow the context window. Prefer selecting/summarizing over dumping.
- `prompt_readable = False` only if `get()` returns markup rather than prompt-ready text.

### Verify and register

After writing: `python -m py_compile /abs/path/{name}.py`. When it compiles, put the
file path in your `done_tool` reasoning so the hook registers it.

---

## Evaluating a memory system

Call `inspect_memory_tool` (or `inspect_tool` on the name) for its registry facts. Score across:
1. **Interface Compliance** — `@MEMORY_SYSTEM.register_module`, subclasses `TieredMemory`/`Memory`, `name` matches the file stem, `enable_evolving` declared.
2. **Code Quality** — valid, clean, no unbounded growth, per-session state correctly keyed.
3. **Retention Quality** — does what it keeps actually serve the next step? Is anything load-bearing dropped? Is anything useless retained?
4. **Boundedness** — does the rendered view stay within a sane size as the session grows?
5. **Integration** — the component shows as registered, and `get()` returns usable text.

The decisive question is not "is the code tidy" but **"after N steps, does the agent still know what it needs?"**

---

## Improving a memory system

The target is named in the task. Call `inspect_memory_tool` FIRST for its file path and `enable_evolving` — if `enable_evolving=False`, the memory system is frozen; do NOT edit it, report and stop. Read the file before editing; make the smallest correct change; preserve `@MEMORY_SYSTEM.register_module`, the class `name`, and the existing method signatures unless the task requires changing them. Verify with `py_compile`, then re-register via the file path in `done_tool` reasoning.

Typical improvements, in order of how often they matter:
- retaining a class of fact that was being dropped (the usual cause of a late-session failure)
- summarizing instead of truncating, so old steps degrade gracefully rather than vanish
- tightening an unbounded section that crowds out everything else

---

## Orchestration (for MetaAgent)

1. **Generate** — dispatch `memory_generate_agent`; it writes `{name}.py` and registers.
2. **Evaluate** — dispatch `memory_evaluate_agent` to score it.
3. **Improve** — dispatch `memory_optimize_agent` with the evaluation; it edits and re-registers.
4. **Repeat** until the memory system is good.

Evidence for a memory defect comes from a **long run**, not a short one: dispatch a task
long enough that early findings must survive to the end, then look for a step that fails
because something established earlier is no longer present in the agent's view.
