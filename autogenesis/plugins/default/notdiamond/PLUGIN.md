---
id: notdiamond
name: Not Diamond
category: agent
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [NOTDIAMOND_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# Not Diamond

Not Diamond tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `notdiamond.notdiamond` | Not Diamond Router | ✅ | Call the right model at the right time with the world |

All 1 tools are implemented.

## Credentials

`NOTDIAMOND_API_KEY`, an `api_key` argument on the call, or a `notdiamond_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
