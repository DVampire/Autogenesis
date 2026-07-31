---
id: elastic
name: Elasticsearch
category: data
type: vectorstore
icon: resources/icon.svg
tools: 3
implemented: 3
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_elasticsearch, langchain_openai]
version: "1.0.0"
---
# Elasticsearch

Elasticsearch tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `elastic.elasticsearch` | Elasticsearch | ✅ | Elasticsearch Vector Store with with advanced, customizable search capabilities. |
| `elastic.opensearch` | OpenSearch | ✅ | OpenSearch |
| `elastic.opensearch_multimodal` | OpenSearch (Multi-Model Multi-Embedding) | ✅ | OpenSearch (Multi-Model Multi-Embedding) |

All 3 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `elastic_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
