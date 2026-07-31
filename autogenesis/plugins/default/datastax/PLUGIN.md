---
id: datastax
name: Astra DB
category: data
type: tool
icon: resources/icon.svg
tools: 10
implemented: 10
credentials: [ASTRA_DB_API_ENDPOINT, ASTRA_DB_APPLICATION_TOKEN, ASTRA_DB_ID, HCD_API_ENDPOINT, OPENAI_API_KEY]
requirements: [astrapy, cassio, dotenv, langchain_astradb, langchain_openai]
version: "1.0.0"
---
# Astra DB

Astra DB tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `datastax.astradb_chatmemory` | Astra DB Chat Memory | ✅ | Retrieves and stores chat messages from Astra DB. |
| `datastax.astradb_cql` | Astra DB CQL | ✅ | Create a tool to get transactional data from DataStax Astra DB CQL Table |
| `datastax.astradb_data_api` | Astra DB Data API | ✅ | Astra DB Data API |
| `datastax.astradb_graph` | Astra DB Graph | ✅ | Implementation of Graph Vector Store using Astra DB |
| `datastax.astradb_tool` | Astra DB Tool | ✅ | Tool to run hybrid vector and metadata search on DataStax Astra DB Collection |
| `datastax.astradb_vectorize` | Astra Vectorize | ✅ | Configuration options for Astra Vectorize server-side embeddings. |
| `datastax.astradb_vectorstore` | Astra DB | ✅ | Ingest and search documents in Astra DB |
| `datastax.dotenv` | Dotenv | ✅ | Load .env file into env vars |
| `datastax.graph_rag` | Graph RAG | ✅ | Graph RAG traversal for vector store. |
| `datastax.hcd` | Hyper-Converged Database | ✅ | Implementation of Vector Store using Hyper-Converged Database (HCD) with search capabilities |

All 10 tools are implemented.

## Credentials

`ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_APPLICATION_TOKEN`, `ASTRA_DB_ID`, `HCD_API_ENDPOINT`, `OPENAI_API_KEY`, an `api_key` argument on the call, or a `datastax_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
