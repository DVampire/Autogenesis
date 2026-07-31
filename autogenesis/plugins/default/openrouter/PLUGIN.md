---
id: openrouter
name: OpenRouter
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENROUTER_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# OpenRouter

OpenRouter tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `openrouter.openrouter` | OpenRouter | ✅ | OpenRouter |

All 1 tools are implemented.

## Credentials

`OPENROUTER_API_KEY`, an `api_key` argument on the call, or a `openrouter_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
