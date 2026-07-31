---
id: anthropic
name: Anthropic
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [ANTHROPIC_API_KEY]
requirements: [langchain_anthropic, langchain_openai]
version: "1.0.0"
---
# Anthropic

Anthropic tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `anthropic.anthropic` | Anthropic | ✅ | Generate text using Anthropic |

All 1 tools are implemented.

## Credentials

`ANTHROPIC_API_KEY`, an `api_key` argument on the call, or a `anthropic_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
