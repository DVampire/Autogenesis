---
id: groq
name: Groq
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [GROQ_API_KEY]
requirements: [langchain_groq, langchain_openai]
version: "1.0.0"
---
# Groq

Groq tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `groq.groq` | Groq | ✅ | Generate text using Groq. |

All 1 tools are implemented.

## Credentials

`GROQ_API_KEY`, an `api_key` argument on the call, or a `groq_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
