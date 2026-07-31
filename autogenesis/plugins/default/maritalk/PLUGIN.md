---
id: maritalk
name: MariTalk
category: data
type: model
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [MARITALK_API_KEY]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# MariTalk

MariTalk tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `maritalk.maritalk` | MariTalk | ✅ | Generates text using MariTalk LLMs. |

All 1 tools are implemented.

## Credentials

`MARITALK_API_KEY`, an `api_key` argument on the call, or a `maritalk_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
