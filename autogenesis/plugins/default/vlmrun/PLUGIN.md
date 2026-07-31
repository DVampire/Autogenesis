---
id: vlmrun
name: VLM Run
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [VLMRUN_API_KEY]
requirements: [vlmrun]
version: "1.0.0"
---
# VLM Run

VLM Run tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `vlmrun.vlmrun_transcription` | VLM Run Transcription | ✅ | Extract structured data from audio and video using [VLM Run AI](https://app.vlm.run) |

All 1 tools are implemented.

## Credentials

`VLMRUN_API_KEY`, an `api_key` argument on the call, or a `vlmrun_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
