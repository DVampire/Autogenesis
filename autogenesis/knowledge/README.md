---
name: knowledge
description: "Retrieval-augmented generation (RAG) over named knowledge bases. A pluggable RagBackend type (bm25, tfidf, …) ranks a corpus; knowledge_manager owns the corpora and exposes ingest/retrieve operations returning the canonical {message, data, files} envelope."
version: 1.0.0
type: module
category: knowledge
requirements: []
metadata: {}
---
# Knowledge

RAG over named knowledge bases. A `RagBackend` is one retrieval *type* — a stateless ranker
`(query, texts, top_k) -> ranked indices`; `knowledge_manager` persists each base's corpus and
delegates ranking to the chosen type. Two operations surface on the canvas: `knowledge_ingest`
and `knowledge_retrieve`. New RAG types drop in by registering a class.
