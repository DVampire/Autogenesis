---
id: perplexity
name: Perplexity
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [PERPLEXITY_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# Perplexity

Perplexity tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `perplexity.perplexity` | Perplexity | ✅ | Generate text using Perplexity LLMs. |

All 1 tools are implemented.

## Credentials

`PERPLEXITY_API_KEY`, an `api_key` argument on the call, or a `perplexity_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
