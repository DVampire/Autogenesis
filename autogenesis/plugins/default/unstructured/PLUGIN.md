---
id: unstructured
name: Unstructured
category: files
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [UNSTRUCTURED_API_KEY]
requirements: [langchain_unstructured]
version: "1.0.0"
---
# Unstructured

Unstructured tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `unstructured.unstructured` | Unstructured API | ✅ | Unstructured API |

All 1 tools are implemented.

## Credentials

`UNSTRUCTURED_API_KEY`, an `api_key` argument on the call, or a `unstructured_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
