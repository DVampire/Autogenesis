---
id: glean
name: Glean
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [GLEAN_ACCESS_TOKEN]
requirements: [httpx]
version: "1.0.0"
---
# Glean

Glean tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `glean.glean_search_api` | Glean Search API | ✅ | Search using Glean |

All 1 tools are implemented.

## Credentials

`GLEAN_ACCESS_TOKEN`, an `api_key` argument on the call, or a `glean_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
