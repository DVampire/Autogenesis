---
id: novita
name: Novita AI
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [NOVITA_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# Novita AI

Novita AI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `novita.novita` | Novita AI | ✅ | Generates text using Novita AI LLMs (OpenAI compatible). |

All 1 tools are implemented.

## Credentials

`NOVITA_API_KEY`, an `api_key` argument on the call, or a `novita_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
