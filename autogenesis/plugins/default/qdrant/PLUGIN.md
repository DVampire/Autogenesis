---
id: qdrant
name: Qdrant
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_openai, langchain_qdrant]
version: "1.0.0"
---
# Qdrant

Qdrant tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `qdrant.qdrant` | Qdrant | ✅ | Qdrant Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `qdrant_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
