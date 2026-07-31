---
name: protocol
description: "Defines typed agent-to-agent conversations over Runtime delivery. Supported channels include delegation, escalation, progress, control, query, and publish/subscribe."
version: 1.0.0
type: module
category: protocol
requirements: []
metadata: {}
---
# Protocol

Defines typed agent-to-agent conversations over Runtime delivery. Supported channels include
delegation, escalation, progress, control, query, and publish/subscribe.

| File | Responsibility |
|---|---|
| `types.py` | Typed protocol messages |
| `server.py` | Channel routing through `protocol_manager` |

Protocol defines what messages mean; Runtime owns how mailboxes and lifecycle delivery work.
