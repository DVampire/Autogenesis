---
name: session
description: "Defines shared invocation context and session-scoped project state."
version: 1.0.0
type: module
category: session
requirements: []
metadata: {}
---
# Session

Defines shared invocation context and session-scoped project state.

| File | Responsibility |
|---|---|
| `types.py` | `BaseContext` and `SessionContext` contracts |
| `project.py` | Session project helpers |

Capability-specific contexts extend these base contracts while retaining consistent session,
workspace, and extra-data semantics.
