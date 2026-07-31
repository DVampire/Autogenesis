---
name: tool_creator_skill
description: Create new tools, improve/optimize existing tools, and evaluate tool quality — the full tool lifecycle in this framework. Use whenever the task involves authoring a new tool (a Python class the agents can call), editing/improving an existing tool, or evaluating/scoring a tool. MetaAgent uses it to orchestrate the create→evaluate→improve loop across sub-agents.
version: 1.0.0
type: [orchestrator, worker]
category: meta
requirements: [cpu]
metadata: {}
---

# Tool Creator

A single skill for the full lifecycle of **tools**: creating, improving, and evaluating them. A tool is a Python class over the shared base `Tool` that an agent invokes with a JSON args object and that returns a `Response`.

## How this skill is used — four roles, one body of knowledge

- **MetaAgent (orchestrator role)** — drives the create→evaluate→improve loop. See **Orchestration**.
- **tool_generate_agent** — reads **Creating a tool**.
- **tool_optimize_agent** — reads **Improving a tool**.
- **tool_evaluate_agent** — reads **Evaluating a tool**.

The sub-agents are headless: each runs one phase autonomously and returns a result.

## Framework conventions (read once)

- A tool is a single Python file: `{extension_root}/tool/{name}.py`.
- **Registration is automatic via a hook**: after writing the file, include its path in your `done_tool` reasoning — the `tool_registration_hook` registers it.

**Start from the template**: read `references/tool_template.py`, copy it, and adapt — it already encodes the convention below.

### Anatomy: description + instruction (progressive disclosure)

A tool splits its docs in two, so the agent's tool_context stays small and the full detail is fetched on demand via `inspect_tool`:
- **`_DESCRIPTION`** — one line: what the tool does. This is all the agent sees in tool_context.
- **`_INSTRUCTION`** — the full instruction in **four markdown blocks**: `## Function`, `## Guidance`, `## Parameters`, `## Example`. Fetched via `inspect_tool` when the agent needs the arguments.

```python
from typing import Any, Dict
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "One line: what the tool does."

_INSTRUCTION = """
## Function
What the tool does, in a sentence or two.

## Guidance
When and how to use it; caveats; when NOT to use it.

## Parameters
- arg_name (type): what it is.

## Example
{"name": "my_tool", "args": {"arg_name": "value"}}
"""


@TOOL.register_module(force=True)
class MyTool(Tool):
    """One-line purpose."""
    name: str = "my_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, arg_name: str, **kwargs) -> Response:
        """Do the work. Args mirror the Parameters block."""
        # ... perform the operation ...
        return Response(type=ResponseType.TOOL, success=True, message="result",
                        data={"arg_name": arg_name})
```

Design principles:
- `__call__` must return a `Response` (`success`, `message`, optional `data`); catch expected failures and return `success=False` with an actionable message rather than raising.
- Keep args explicit and JSON-friendly. Document every arg in the `## Parameters` block.
- If the tool needs the current session, accept `ctx` via `**kwargs`. Do heavyweight imports **inside** `__call__` to avoid circular imports at module load.

### Verify and register

After writing: `python -m py_compile /abs/path/{name}.py`. When it compiles, put the path in your `done_tool` reasoning so the hook registers it.

---

## Evaluating a tool

Call `inspect_tool` on the target — it returns the full instruction plus registry facts (version, enable_evolving, source path). Score across:
1. **Interface Compliance** — `@TOOL.register_module`, subclass `Tool`, has `name`/`description`/`instruction`, `__call__` returns a `Response`.
2. **Code Quality** — valid, clean, proper error handling (failures returned as `success=False`, not raised).
3. **Instruction Quality** — `_INSTRUCTION` has the four blocks (Function/Guidance/Parameters/Example); every parameter documented; example is valid JSON.
4. **Integration** — `inspect_tool` shows it registered.
5. **Execution** — a valid call path; where feasible, run the tool on a sample input and check the `Response`.

---

## Improving a tool

The target is named in the task. Call `inspect_tool` FIRST for its source path and `enable_evolving` — if `enable_evolving=False`, the tool is frozen; do NOT edit it, report and stop. Read the source before editing; make the smallest correct change; preserve `@TOOL.register_module` and `name`; keep `_DESCRIPTION` short and `_INSTRUCTION`'s four blocks intact. Verify with `py_compile`, then re-register via the path in `done_tool` reasoning.

---

## Orchestration (for MetaAgent)

1. **Generate** — dispatch `tool_generate_agent`; it writes the tool file and registers.
2. **Evaluate** — dispatch `tool_evaluate_agent` (optionally after a sample call) to score.
3. **Improve** — dispatch `tool_optimize_agent` with the evaluation; it edits and re-registers.
4. **Repeat** until the tool is good.

## Reference files

- `references/tool_template.py` — a ready-to-copy tool class (the `_DESCRIPTION`/`_INSTRUCTION` split + `__call__` returning a `Response`).
