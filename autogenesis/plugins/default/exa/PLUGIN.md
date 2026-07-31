---
id: exa
name: Exa
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [EXA_API_KEY]
requirements: [exa_py]
version: "1.0.0"
---
# Exa

Exa tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `exa.exa_search` | Exa Search | ✅ | Exa search and contents tools for agents and MCP clients. |

All 1 tools are implemented.

## Credentials

`EXA_API_KEY`, an `api_key` argument on the call, or a `exa_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
