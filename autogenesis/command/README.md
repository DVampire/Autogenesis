---
name: command
description: "Models user-facing commands, their contexts, and command dispatch. Built-in command implementations are registered from `default/`."
version: 1.0.0
type: module
category: command
requirements: []
metadata: {}
---
# Command

Models user-facing commands, their contexts, and command dispatch. Built-in command
implementations are registered from `default/`.

| File | Responsibility |
|---|---|
| `types.py` | Command types and invocation context |
| `context.py` | Registration and lookup state |
| `server.py` | Public `command_manager` facade |

Commands translate explicit user operations into framework calls; they should not duplicate
Agent planning or Tool execution logic.
