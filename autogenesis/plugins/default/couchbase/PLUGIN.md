---
id: couchbase
name: Couchbase
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [couchbase, langchain_couchbase, langchain_openai]
version: "1.0.0"
---
# Couchbase

Couchbase tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `couchbase.couchbase` | Couchbase | ✅ | Couchbase Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `couchbase_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
