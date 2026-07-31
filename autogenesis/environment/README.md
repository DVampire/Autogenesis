---
name: environment
description: "Defines stateful execution environments and their callable actions. Environment actions are exposed individually with declared or inferred parameter schemas."
version: 1.0.0
type: module
category: environment
requirements: []
metadata: {}
---
# Environment

Defines stateful execution environments and their callable actions. Environment actions
are exposed individually with declared or inferred parameter schemas.

| File | Responsibility |
|---|---|
| `types.py` | Environment, action, configuration, and context contracts |
| `context.py` | Registration and environment instance lifecycle |
| `server.py` | Public API, state access, action invocation, and schemas |
| `default/` | Built-in browser and artifact-rendering environments |

Environment owns external state and action semantics; multi-step planning belongs to Agent
or Workflow.
