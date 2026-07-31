---
id: confluence
name: Confluence
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [CONFLUENCE_API_KEY]
requirements: [langchain_community]
version: "1.0.0"
---
# Confluence

Confluence tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `confluence.confluence` | Confluence | ✅ | Confluence wiki collaboration platform |

All 1 tools are implemented.

## Credentials

`CONFLUENCE_API_KEY`, an `api_key` argument on the call, or a `confluence_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
