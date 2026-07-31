---
id: chroma
name: Chroma
category: data
type: vectorstore
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [OPENAI_API_KEY]
requirements: [chromadb, langchain_chroma, langchain_openai]
version: "1.0.0"
---
# Chroma

Chroma tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `chroma.chroma` | Chroma DB | ✅ | Chroma Vector Store with search capabilities |
| `chroma.local_db` | Local DB | ✅ | Local Vector Store with search capabilities |

All 2 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `chroma_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
