---
id: baidu
name: Qianfan
category: data
type: model
tools: 1
implemented: 1
credentials: [QIANFAN_AK, QIANFAN_SK]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# Qianfan

Qianfan tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `baidu.baidu_qianfan_chat` | Qianfan | ✅ | Generate text using Baidu Qianfan LLMs. |

All 1 tools are implemented.

## Credentials

`QIANFAN_AK`, `QIANFAN_SK`, an `api_key` argument on the call, or a `baidu_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
