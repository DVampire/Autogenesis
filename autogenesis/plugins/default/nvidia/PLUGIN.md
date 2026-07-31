---
id: nvidia
name: NVIDIA
category: data
type: tool
icon: resources/icon.svg
tools: 5
implemented: 5
credentials: [NVIDIA_API_KEY]
requirements: [langchain_core, langchain_nvidia_ai_endpoints, langchain_openai, nv_ingest_client]
version: "1.0.0"
---
# NVIDIA

NVIDIA tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `nvidia.nvidia` | NVIDIA | ✅ | Generates text using NVIDIA LLMs. |
| `nvidia.nvidia_embedding` | NVIDIA Embeddings | ✅ | Generate embeddings using NVIDIA models. |
| `nvidia.nvidia_ingest` | NVIDIA Retriever Extraction | ✅ | Multi-modal data extraction from documents using NVIDIA |
| `nvidia.nvidia_rerank` | NVIDIA Rerank | ✅ | Rerank documents using the NVIDIA API. |
| `nvidia.system_assist` | NVIDIA System-Assist | ✅ | NVIDIA System-Assist |

All 5 tools are implemented.

## Credentials

`NVIDIA_API_KEY`, an `api_key` argument on the call, or a `nvidia_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
