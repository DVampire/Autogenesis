---
id: twelvelabs
name: TwelveLabs
category: data
type: tool
icon: resources/icon.svg
tools: 7
implemented: 7
credentials: [TWELVELABS_API_KEY, TWELVE_LABS_API_KEY]
requirements: [twelvelabs]
version: "1.0.0"
---
# TwelveLabs

TwelveLabs tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `twelvelabs.convert_astra_results` | Convert Astra DB to Pegasus Input | ✅ | Converts Astra DB search results to inputs compatible with TwelveLabs Pegasus. |
| `twelvelabs.pegasus_index` | TwelveLabs Pegasus Index Video | ✅ | Index videos using TwelveLabs and add the video_id to metadata. |
| `twelvelabs.split_video` | Split Video | ✅ | Split a video into multiple clips of specified duration. |
| `twelvelabs.text_embeddings` | TwelveLabs Text Embeddings | ✅ | Generate embeddings using TwelveLabs text embedding models. |
| `twelvelabs.twelvelabs_pegasus` | TwelveLabs Pegasus | ✅ | Chat with videos using TwelveLabs Pegasus API. |
| `twelvelabs.video_embeddings` | TwelveLabs Video Embeddings | ✅ | Generate embeddings from videos using TwelveLabs video embedding models. |
| `twelvelabs.video_file` | Video File | ✅ | Load a video file in common video formats. |

All 7 tools are implemented.

## Credentials

`TWELVELABS_API_KEY`, `TWELVE_LABS_API_KEY`, an `api_key` argument on the call, or a `twelvelabs_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
