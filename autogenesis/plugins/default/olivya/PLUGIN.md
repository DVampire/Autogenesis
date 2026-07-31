---
id: olivya
name: Olivya
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OLIVYA_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# Olivya

Olivya tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `olivya.olivya` | Place Call | ✅ | A component to create an outbound call request from Olivya |

All 1 tools are implemented.

## Credentials

`OLIVYA_API_KEY`, an `api_key` argument on the call, or a `olivya_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
