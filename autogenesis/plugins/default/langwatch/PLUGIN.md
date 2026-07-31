---
id: langwatch
name: LangWatch
category: evaluation
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [LANGWATCH_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# LangWatch

LangWatch tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `langwatch.langwatch` | LangWatch Evaluator | ✅ | Evaluates various aspects of language models using LangWatch |

All 1 tools are implemented.

## Credentials

`LANGWATCH_API_KEY`, an `api_key` argument on the call, or a `langwatch_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
