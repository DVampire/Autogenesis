---
id: cleanlab
name: Cleanlab
category: evaluation
type: tool
tools: 3
implemented: 3
credentials: [CLEANLAB_API_KEY, CLEANLAB_TLM_API_KEY]
requirements: [cleanlab_tlm]
version: "1.0.0"
---
# Cleanlab

Cleanlab tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `cleanlab.cleanlab_evaluator` | Cleanlab Evaluator | ✅ | Evaluates any LLM response using Cleanlab and outputs trust score and explanation. |
| `cleanlab.cleanlab_rag_evaluator` | Cleanlab RAG Evaluator | ✅ | Evaluates context, query, and response from a RAG pipeline using Cleanlab and outputs trust metrics. |
| `cleanlab.cleanlab_remediator` | Cleanlab Remediator | ✅ | Cleanlab Remediator |

All 3 tools are implemented.

## Credentials

`CLEANLAB_API_KEY`, `CLEANLAB_TLM_API_KEY`, an `api_key` argument on the call, or a `cleanlab_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
