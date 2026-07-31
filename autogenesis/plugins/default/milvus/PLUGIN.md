---
id: milvus
name: Milvus
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_milvus, langchain_openai]
version: "1.0.0"
---
# Milvus

Milvus tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `milvus.milvus` | Milvus | ✅ | Milvus vector store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `milvus_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
