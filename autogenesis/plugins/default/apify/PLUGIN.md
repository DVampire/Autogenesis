---
id: apify
name: Apify
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [APIFY_API_TOKEN, APIFY_TOKEN]
requirements: [apify_client]
version: "1.0.0"
---
# Apify

Apify tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `apify.apify_actor` | Apify Actors | ✅ | Apify Actors |

All 1 tools are implemented.

## Credentials

`APIFY_API_TOKEN`, `APIFY_TOKEN`, an `api_key` argument on the call, or a `apify_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
