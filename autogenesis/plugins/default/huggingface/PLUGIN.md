---
id: huggingface
name: Hugging Face
category: data
type: model
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [HUGGINGFACEHUB_API_TOKEN]
requirements: [langchain_community, langchain_huggingface, langchain_openai]
version: "1.0.0"
---
# Hugging Face

Hugging Face tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `huggingface.huggingface` | Hugging Face | ✅ | Generate text using Hugging Face Inference APIs. |
| `huggingface.huggingface_inference_api` | Hugging Face Embeddings Inference | ✅ | Generate embeddings using Hugging Face Text Embeddings Inference (TEI) |

All 2 tools are implemented.

## Credentials

`HUGGINGFACEHUB_API_TOKEN`, an `api_key` argument on the call, or a `huggingface_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
