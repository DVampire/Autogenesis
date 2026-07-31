---
name: trajectory
description: "Projects agent runs into reward-annotated, step-level training records and exports formats used by supervised fine-tuning or reinforcement learning pipelines."
version: 1.0.0
type: module
category: trajectory
requirements: []
metadata: {}
---
# Trajectory

Projects agent runs into reward-annotated, step-level training records and exports formats
used by supervised fine-tuning or reinforcement learning pipelines.

| Path | Responsibility |
|---|---|
| `types.py` | Trajectory, step, context, and export contracts |
| `server.py` | Capture, persistence, and export facade |
| `default/` | Built-in output formats such as VERL |

Trajectory consumes lifecycle evidence but does not participate in runtime control flow.
