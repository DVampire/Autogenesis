---
id: aiml
name: AI/ML API
category: data
type: model
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [AIML_API_KEY]
requirements: [langchain_openai]
version: "1.0.0"
---
# AI/ML API

AI/ML API tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `aiml.aiml` | AI/ML API | ✅ | Generates text using AI/ML API LLMs. |
| `aiml.aiml_embeddings` | AI/ML API Embeddings | ✅ | Generate embeddings using the AI/ML API. |

All 2 tools are implemented.

## Credentials

`AIML_API_KEY`, an `api_key` argument on the call, or a `aiml_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
