---
name: model
description: "Provides the model registry, role-based selection, API-key pooling, and provider-neutral generation interface."
version: 1.0.0
type: module
category: model
requirements: []
metadata: {}
---
# Model

Provides the model registry, role-based selection, API-key pooling, and provider-neutral
generation interface.

| Path | Responsibility |
|---|---|
| `types.py` | Model configuration contracts |
| `config.py` | Model configuration helpers |
| `context.py` | Registry, selection, and API-key lifecycle |
| `server.py` | Stable `model_manager` facade |
| `anthropic/`, `google/`, `openai/`, `openrouter/` | Provider serializers and clients |

Provider packages adapt wire protocols; Agents consume only the shared Manager contract.
