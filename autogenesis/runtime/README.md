---
name: runtime
description: "Owns live Agent references, mailboxes, lifecycle state, and the event pump that advances registered Agent instances."
version: 1.0.0
type: module
category: runtime
requirements: []
metadata: {}
---
# Runtime

Owns live Agent references, mailboxes, lifecycle state, and the event pump that advances
registered Agent instances.

| File | Responsibility |
|---|---|
| `types.py` | Agent references, statuses, and runtime messages |
| `pump.py` | Mailbox event pump |
| `server.py` | Spawn, send, stop, wait, and lookup operations |

Runtime moves events and owns process-local execution state. Protocol defines conversation
semantics; Workflow interprets persisted orchestration programs above it.
