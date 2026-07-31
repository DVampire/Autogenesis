---
name: trace
description: "Captures structured lifecycle events, persists them, and fans them out to subscribers."
version: 1.0.0
type: module
category: trace
requirements: []
metadata: {}
---
# Trace

Captures structured lifecycle events, persists them, and fans them out to subscribers.

| Path | Responsibility |
|---|---|
| `types.py` | Trace event contracts and event factories |
| `writer.py` | Durable event writing |
| `server.py` | Trace manager lifecycle and the subscriber fan-out |

Trace owns no UI of its own. Events reach a browser through `subscribe()` —
the Gateway forwards them to the web frontend — and are persisted as
`<log_root>/trace/<session_id>.jsonl` for offline inspection.

Trace is observational. It must not change Agent, Runtime, or Workflow execution semantics.
