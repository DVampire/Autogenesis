---
id: cometapi
name: CometAPI
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [COMETAPI_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# CometAPI

CometAPI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `cometapi.cometapi` | CometAPI | ✅ | All AI Models in One API 500+ AI Models |

All 1 tools are implemented.

## Credentials

`COMETAPI_API_KEY`, an `api_key` argument on the call, or a `cometapi_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
