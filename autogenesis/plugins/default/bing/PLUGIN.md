---
id: bing
name: Bing
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [BING_API_KEY, BING_SUBSCRIPTION_KEY]
requirements: [langchain_community]
version: "1.0.0"
---
# Bing

Bing tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `bing.bing_search_api` | Bing Search API | ✅ | Call the Bing Search API. |

All 1 tools are implemented.

## Credentials

`BING_API_KEY`, `BING_SUBSCRIPTION_KEY`, an `api_key` argument on the call, or a `bing_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
