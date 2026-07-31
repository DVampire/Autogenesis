---
name: dynamic
description: "Loads generated Python source into controlled runtime modules and derives callable metadata such as parameters, argument models, and function-calling schemas."
version: 1.0.0
type: module
category: dynamic
requirements: []
metadata: {}
---
# Dynamic

Loads generated Python source into controlled runtime modules and derives callable metadata
such as parameters, argument models, and function-calling schemas.

| File | Responsibility |
|---|---|
| `types.py` | Dynamic-module data contracts |
| `server.py` | `DynamicModuleManager`, source loading, and introspection |

Dynamic loading supplies implementation classes to owning Managers; it does not register or
execute capabilities by itself.
