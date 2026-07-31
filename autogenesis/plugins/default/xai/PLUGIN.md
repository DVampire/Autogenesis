---
id: xai
name: xAI
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [XAI_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# xAI

xAI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `xai.xai` | xAI | ✅ | Generates text using xAI models like Grok. |

All 1 tools are implemented.

## Credentials

`XAI_API_KEY`, an `api_key` argument on the call, or a `xai_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
