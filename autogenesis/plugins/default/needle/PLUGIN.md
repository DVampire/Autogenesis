---
id: needle
name: Needle
category: data
type: vectorstore
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# Needle

Needle tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `needle.needle` | Needle Retriever | ✅ | A retriever that uses the Needle API to search collections. |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `needle_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
