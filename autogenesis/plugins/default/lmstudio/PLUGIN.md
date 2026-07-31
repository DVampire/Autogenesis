---
id: lmstudio
name: LM Studio
category: data
type: embedding
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [LMSTUDIO_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# LM Studio

LM Studio tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `lmstudio.lmstudioembeddings` | LM Studio Embeddings | ✅ | Generate embeddings using LM Studio. |
| `lmstudio.lmstudiomodel` | LM Studio | ✅ | Generate text using LM Studio Local LLMs. |

All 2 tools are implemented.

## Credentials

`LMSTUDIO_API_KEY`, an `api_key` argument on the call, or a `lmstudio_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
