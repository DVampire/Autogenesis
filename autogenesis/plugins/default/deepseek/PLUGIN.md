---
id: deepseek
name: DeepSeek
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [DEEPSEEK_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# DeepSeek

DeepSeek tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `deepseek.deepseek` | DeepSeek | ✅ | Generate text using DeepSeek LLMs. |

All 1 tools are implemented.

## Credentials

`DEEPSEEK_API_KEY`, an `api_key` argument on the call, or a `deepseek_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
