---
id: ibm
name: IBM DB2
category: data
type: vectorstore
tools: 3
implemented: 3
credentials: [OPENAI_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL]
requirements: [ibm_db_dbi, langchain_db2, langchain_ibm, langchain_openai]
version: "1.0.0"
---
# IBM DB2

IBM DB2 tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `ibm.db2_vector` | IBM Db2 Vector Store | ✅ | IBM Db2 Vector Store |
| `ibm.watsonx` | IBM watsonx.ai | ✅ | Generate text using IBM watsonx.ai foundation models. |
| `ibm.watsonx_embeddings` | IBM watsonx.ai Embeddings | ✅ | Generate embeddings using IBM watsonx.ai models. |

All 3 tools are implemented.

## Credentials

`OPENAI_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, an `api_key` argument on the call, or a `ibm_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
