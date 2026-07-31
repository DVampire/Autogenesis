---
id: faiss
name: FAISS
category: data
type: vectorstore
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# FAISS

FAISS tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `faiss.faiss` | FAISS | ✅ | FAISS Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `faiss_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
