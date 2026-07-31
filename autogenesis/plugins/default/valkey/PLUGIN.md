---
id: valkey
name: Valkey
category: data
type: vectorstore
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# Valkey

Valkey tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `valkey.valkey` | Valkey | ✅ | Implementation of Vector Store using Valkey |
| `valkey.valkey_chat` | Valkey Chat Memory | ✅ | Retrieves and stores chat messages from Valkey. |

All 2 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `valkey_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
