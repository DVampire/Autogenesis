---
id: oracle
name: Oracle
category: data
type: embedding
icon: resources/icon.svg
tools: 3
implemented: 3
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai, oracledb]
version: "1.0.0"
---
# Oracle

Oracle tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `oracle.oracledb_embeddings` | Oracle Embeddings | ✅ | Generate embeddings using Oracle AI Vector Search. |
| `oracle.oracledb_loaders` | Oracle Doc Loader | ✅ | Read documents from Oracle Database using OracleDocLoader. |
| `oracle.oraclevs` | Oracle Vector Store | ✅ | Oracle vector store with search capabilities |

All 3 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `oracle_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
