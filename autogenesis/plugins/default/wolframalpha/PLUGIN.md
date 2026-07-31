---
id: wolframalpha
name: WolframAlpha
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [WOLFRAM_ALPHA_APPID]
requirements: [langchain_community]
version: "1.0.0"
---
# WolframAlpha

WolframAlpha tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `wolframalpha.wolfram_alpha_api` | WolframAlpha API | ✅ | WolframAlpha API |

All 1 tools are implemented.

## Credentials

`WOLFRAM_ALPHA_APPID`, an `api_key` argument on the call, or a `wolframalpha_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
