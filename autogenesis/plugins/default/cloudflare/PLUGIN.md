---
id: cloudflare
name: Cloudflare
category: knowledge
type: embedding
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [CLOUDFLARE_ACCOUNT_ID]
requirements: [langchain_community]
version: "1.0.0"
---
# Cloudflare

Cloudflare tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `cloudflare.cloudflare` | Cloudflare Workers AI Embeddings | ✅ | Generate embeddings using Cloudflare Workers AI models. |

All 1 tools are implemented.

## Credentials

`CLOUDFLARE_ACCOUNT_ID`, an `api_key` argument on the call, or a `cloudflare_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
