---
id: serpapi
name: SerpAPI
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [SERPAPI_API_KEY, SERP_API_KEY]
requirements: [langchain_community]
version: "1.0.0"
---
# SerpAPI

SerpAPI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `serpapi.serp` | Serp Search API | ✅ | Call Serp Search API with result limiting |

All 1 tools are implemented.

## Credentials

`SERPAPI_API_KEY`, `SERP_API_KEY`, an `api_key` argument on the call, or a `serpapi_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
