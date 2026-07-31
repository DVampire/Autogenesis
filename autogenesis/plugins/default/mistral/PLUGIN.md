---
id: mistral
name: MistralAI
category: data
type: model
tools: 2
implemented: 2
credentials: [MISTRAL_API_KEY]
requirements: [langchain_mistralai, langchain_openai]
version: "1.0.0"
---
# MistralAI

MistralAI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `mistral.mistral` | MistralAI | ✅ | Generates text using MistralAI LLMs. |
| `mistral.mistral_embeddings` | MistralAI Embeddings | ✅ | Generate embeddings using MistralAI models. |

All 2 tools are implemented.

## Credentials

`MISTRAL_API_KEY`, an `api_key` argument on the call, or a `mistral_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
