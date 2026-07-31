---
id: tavily
name: Tavily
category: data
type: tool
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [TAVILY_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# Tavily

Web search and page extraction, tuned for LLM retrieval.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `tavily.tavily_extract` | Tavily Extract | ✅ | Fetch one or more URLs and return their readable text content. |
| `tavily.tavily_search` | Tavily Search | ✅ | Search the web and return ranked results, optionally with a synthesised answer. |

All 2 tools are implemented.

## Credentials

`TAVILY_API_KEY`, an `api_key` argument on the call, or a `tavily_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
