---
name: task
description: "Models tasks, their priorities and statuses, loads task documents, and resolves CLI task input into normalized records."
version: 1.0.0
type: module
category: task
requirements: []
metadata: {}
---
# Task

Models tasks, their priorities and statuses, loads task documents, and resolves CLI task
input into normalized records.

| File | Responsibility |
|---|---|
| `types.py` | Task contracts and enums |
| `server.py` | Task records, categories, and manager operations |
| `loader.py` | HTML/Markdown task document loading |
| `run_input.py` | CLI arguments and task resolution |

Task records describe work; Agent and Workflow own execution behavior.
