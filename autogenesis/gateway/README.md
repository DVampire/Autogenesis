---
name: gateway
description: "Defines the versioned boundary used by interactive clients to communicate with Autogenesis. The package uses a lazy public import so importing `autogenesis.gateway` does not eagerly start transport dependencies."
version: 1.0.0
type: module
category: gateway
requirements: []
metadata: {}
---
# Gateway

Defines the versioned boundary used by interactive clients to communicate with Autogenesis.
The package uses a lazy public import so importing `autogenesis.gateway` does not eagerly
start transport dependencies.

| File | Responsibility |
|---|---|
| `protocol.py` | Client-facing request and event contracts |
| `service.py` | Gateway application service |
| `transport.py` | Transport adaptation |
| `__main__.py` | Standalone gateway entry point |

Gateway adapts external clients; internal agent messaging belongs to Protocol and Runtime.
