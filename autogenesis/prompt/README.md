---
name: prompt
description: "Loads, versions, and renders HTML-native prompts and reusable prompt modules."
version: 1.0.0
type: module
category: prompt
requirements: []
metadata: {}
---
# Prompt

Loads, versions, and renders HTML-native prompts and reusable prompt modules.

| Path | Responsibility |
|---|---|
| `types.py` | Prompt and configuration contracts |
| `context.py` | Discovery, parsing, and lifecycle state |
| `server.py` | Public `prompt_manager` facade |
| `default/` | Built-in agent prompts |
| `module/` | Reusable prompt fragments |

Prompts carry compact capability discovery context. Complete callable parameter schemas are
provided separately by capability Managers and loaded on demand by inspect tools.
