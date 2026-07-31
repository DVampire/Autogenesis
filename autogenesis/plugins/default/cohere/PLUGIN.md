---
id: cohere
name: Cohere
category: data
type: embedding
icon: resources/icon.svg
tools: 3
implemented: 3
credentials: [COHERE_API_KEY]
requirements: [langchain_cohere, langchain_core, langchain_openai]
version: "1.0.0"
---
# Cohere

Cohere tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `cohere.cohere_embeddings` | Cohere Embeddings | ✅ | Generate embeddings using Cohere models. |
| `cohere.cohere_models` | Cohere Language Models | ✅ | Generate text using Cohere LLMs. |
| `cohere.cohere_rerank` | Cohere Rerank | ✅ | Rerank documents using the Cohere API. |

All 3 tools are implemented.

## Credentials

`COHERE_API_KEY`, an `api_key` argument on the call, or a `cohere_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
