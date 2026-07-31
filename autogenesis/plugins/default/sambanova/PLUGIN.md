---
id: sambanova
name: SambaNova
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [SAMBANOVA_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# SambaNova

SambaNova tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `sambanova.sambanova` | SambaNova | ✅ | Generate text using Sambanova LLMs. |

All 1 tools are implemented.

## Credentials

`SAMBANOVA_API_KEY`, an `api_key` argument on the call, or a `sambanova_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
