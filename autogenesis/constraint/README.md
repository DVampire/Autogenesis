---
name: constraint
description: "Defines enforceable runtime budgets and status reporting. Built-ins cover step, token, and wall-time limits."
version: 1.0.0
type: module
category: constraint
requirements: []
metadata: {}
---
# Constraint

Defines enforceable runtime budgets and status reporting. Built-ins cover step, token, and
wall-time limits.

| File | Responsibility |
|---|---|
| `types.py` | Constraint contracts, contexts, status, and rendering |
| `context.py` | Registered constraint state |
| `server.py` | Public `constraint_manager` facade |
| `default/` | Standard constraint implementations |

Constraints decide whether execution may continue; the Agent and Runtime loops decide when
to perform those checks.
