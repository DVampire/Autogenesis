---
id: litellm
name: LiteLLM Proxy
category: data
type: model
tools: 1
implemented: 1
credentials: [LITELLM_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# LiteLLM Proxy

LiteLLM Proxy tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `litellm.litellm_proxy` | LiteLLM Proxy | ✅ | Generate text using any LLM provider via a LiteLLM proxy with virtual key authentication. |

All 1 tools are implemented.

## Credentials

`LITELLM_API_KEY`, an `api_key` argument on the call, or a `litellm_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
