---
name: connector
description: "Integrates external capability providers, primarily MCP servers. A connector can expose multiple actions; each action is projected as its own callable function and retains the provider's input schema when available."
version: 1.0.0
type: module
category: connector
requirements: []
metadata: {}
---
# Connector

Integrates external capability providers, primarily MCP servers. A connector can expose
multiple actions; each action is projected as its own callable function and retains the
provider's input schema when available.

| File | Responsibility |
|---|---|
| `types.py` | Connector configuration and action metadata |
| `context.py` | Connection lifecycle, discovery, and invocation |
| `server.py` | Public manager API and per-action schemas |
| `default/` | Built-in connector manifests and their collection README |

Connector owns transport adaptation, not orchestration policy or credential persistence.
