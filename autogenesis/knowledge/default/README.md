---
name: knowledge_default
description: "Registers the built-in RAG retrieval types (bm25 sparse lexical, tfidf cosine). Implementations conform to the RagBackend contract of the parent Knowledge module."
version: 1.0.0
type: collection
category: knowledge
requirements: []
metadata: {}
---
# Built-in RAG types

Registers the offline retrieval backends `bm25` (rank_bm25) and `tfidf` (scikit-learn cosine).
New types (e.g. an embedding backend via model_manager) drop in by registering a class.
