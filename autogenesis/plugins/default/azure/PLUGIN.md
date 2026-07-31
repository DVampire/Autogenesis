---
id: azure
name: Azure OpenAI
category: data
type: model
tools: 2
implemented: 2
credentials: [AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT]
requirements: [langchain_openai]
version: "1.0.0"
---
# Azure OpenAI

Azure OpenAI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `azure.azure_openai` | Azure OpenAI | ✅ | Generate text using Azure OpenAI LLMs. |
| `azure.azure_openai_embeddings` | Azure OpenAI Embeddings | ✅ | Generate embeddings using Azure OpenAI models. |

All 2 tools are implemented.

## Credentials

`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, an `api_key` argument on the call, or a `azure_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
