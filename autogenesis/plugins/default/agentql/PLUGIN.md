---
id: agentql
name: AgentQL
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [AGENTQL_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# AgentQL

AgentQL tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `agentql.agentql_api` | Extract Web Data | ✅ | Extracts structured data from a web page using an AgentQL query or a Natural Language description. |

All 1 tools are implemented.

## Credentials

`AGENTQL_API_KEY`, an `api_key` argument on the call, or a `agentql_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
