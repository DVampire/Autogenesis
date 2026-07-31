---
id: searchapi
name: SearchApi
category: data
type: tool
tools: 1
implemented: 1
credentials: [SEARCHAPI_API_KEY]
requirements: [langchain_community]
version: "1.0.0"
---
# SearchApi

SearchApi tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `searchapi.search` | SearchApi | ✅ | Calls the SearchApi API with result limiting. Supports Google, Bing and DuckDuckGo. |

All 1 tools are implemented.

## Credentials

`SEARCHAPI_API_KEY`, an `api_key` argument on the call, or a `searchapi_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
