---
id: jigsawstack
name: JigsawStack
category: data
type: tool
icon: resources/icon.svg
tools: 11
implemented: 11
credentials: [JIGSAWSTACK_API_KEY]
requirements: [jigsawstack]
version: "1.0.0"
---
# JigsawStack

JigsawStack tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `jigsawstack.ai_scrape` | AI Scraper | ✅ | Scrape any website instantly and get consistent structured data \\\\\\n        in seconds without writing any css selector code |
| `jigsawstack.ai_web_search` | AI Web Search | ✅ | Effortlessly search the Web and get access to high-quality results powered with AI. |
| `jigsawstack.file_read` | File Read | ✅ | Read any previously uploaded file seamlessly from \\\\\\n        JigsawStack File Storage and use it in your AI applications. |
| `jigsawstack.file_upload` | File Upload | ✅ | Store any file seamlessly on JigsawStack File Storage and use it in your AI applications. \\\\\\n        Supports various file types including images, documents, and more. |
| `jigsawstack.image_generation` | Image Generation | ✅ | Generate an image based on the given text by employing AI models like Flux, \\\\\\n        Stable Diffusion, and other top models. |
| `jigsawstack.nsfw` | NSFW Detection | ✅ | Detect if image/video contains NSFW content |
| `jigsawstack.object_detection` | Object Detection | ✅ | Perform object detection on images using JigsawStack |
| `jigsawstack.sentiment` | Sentiment Analysis | ✅ | Analyze sentiment of text using JigsawStack AI |
| `jigsawstack.text_to_sql` | Text to SQL | ✅ | Convert natural language to SQL queries using JigsawStack AI |
| `jigsawstack.text_translate` | Text Translate | ✅ | Translate text from one language to another with support for multiple text formats. |
| `jigsawstack.vocr` | VOCR | ✅ | Extract data from any document type in a consistent structure with fine-tuned \\\\\\n        vLLMs for the highest accuracy |

All 11 tools are implemented.

## Credentials

`JIGSAWSTACK_API_KEY`, an `api_key` argument on the call, or a `jigsawstack_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
