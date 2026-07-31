---
id: pinecone
name: Pinecone
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_openai, langchain_pinecone]
version: "1.0.0"
---
# Pinecone

Pinecone tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `pinecone.pinecone` | Pinecone | ✅ | Pinecone Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `pinecone_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
