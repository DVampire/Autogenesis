---
name: sandbox
description: "Defines isolated command execution, managed sandbox processes, and staged project validation."
version: 1.0.0
type: module
category: sandbox
requirements: []
metadata: {}
---
# Sandbox

Defines isolated command execution, managed sandbox processes, and staged project validation.

| File | Responsibility |
|---|---|
| `types.py` | Sandbox configuration and execution results |
| `server.py` | Public `sandbox_manager` facade |
| `process.py` | Managed sandbox-server processes |
| `project.py` | Project staging and validation helpers |
| `default/` | Built-in sandbox backends |

Permission decides whether an operation is allowed; Sandbox provides the execution boundary.
