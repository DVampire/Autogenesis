---
id: empiriolabs
name: EmpirioLabs
category: agent
type: tool
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [EMPIRIOLABS_API_KEY]
requirements: [httpx, langchain_openai]
version: "1.0.0"
---
# EmpirioLabs

EmpirioLabs tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `empiriolabs.empiriolabs` | EmpirioLabs AI | ✅ | Generates text using EmpirioLabs AI LLMs (OpenAI compatible). |
| `empiriolabs.empiriolabs_image_generation` | EmpirioLabs AI Image Generation | ✅ | Generate an image from a text prompt using EmpirioLabs AI image models such as Seedream, \\\\\\n        Qwen-Image, FLUX, Nova Canvas, and HunyuanImage. |

All 2 tools are implemented.

## Credentials

`EMPIRIOLABS_API_KEY`, an `api_key` argument on the call, or a `empiriolabs_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
