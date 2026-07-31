---
name: deploy
description: "Deploys web artifacts from controlled source directories and records their URLs, health, resources, and lifecycle state."
version: 1.0.0
type: module
category: deploy
requirements: []
metadata: {}
---
# Deploy

Deploys web artifacts from controlled source directories and records their URLs, health,
resources, and lifecycle state.

| File | Responsibility |
|---|---|
| `types.py` | Deployment requests, specifications, records, and statuses |
| `server.py` | Public `deployment_manager` and lifecycle operations |
| `default/` | Built-in deployment profiles |

Deployment coordinates a target backend; process isolation and command execution belong to
the Sandbox module.
