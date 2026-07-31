---
id: openai
name: OpenAI
category: data
type: embedding
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [OPENAI_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# OpenAI

OpenAI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `openai.openai` | OpenAI Embeddings | ✅ | Generate embeddings using OpenAI models. |
| `openai.openai_chat_model` | OpenAI | ✅ | Generates text using OpenAI LLMs. |

All 2 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `openai_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
