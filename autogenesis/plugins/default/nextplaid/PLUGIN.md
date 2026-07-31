---
id: nextplaid
name: NextPlaid
category: data
type: tool
tools: 2
implemented: 2
credentials: [NEXTPLAID_API_KEY, VLLM_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# NextPlaid

NextPlaid tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `nextplaid.nextplaid` | NextPlaid | ✅ | NextPlaid |
| `nextplaid.vllm_multivector_embeddings` | vLLM Multivector Embeddings | ✅ | vLLM Multivector Embeddings |

All 2 tools are implemented.

## Credentials

`NEXTPLAID_API_KEY`, `VLLM_API_KEY`, an `api_key` argument on the call, or a `nextplaid_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
