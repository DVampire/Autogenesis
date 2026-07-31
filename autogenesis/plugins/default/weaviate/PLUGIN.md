---
id: weaviate
name: Weaviate
category: data
type: vectorstore
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_openai, langchain_weaviate, weaviate]
version: "1.0.0"
---
# Weaviate

Weaviate tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `weaviate.weaviate` | Weaviate | ✅ | Weaviate Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `weaviate_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
