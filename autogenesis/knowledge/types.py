"""Type definitions for the knowledge module (RAG).

A **RagBackend** is one *type* of retrieval (bm25, tfidf, embedding, …) — a
pluggable, stateless ranker: given a query and a corpus of texts it returns the
top-k most relevant, as ``(index, score)`` pairs. The :class:`KnowledgeManager`
owns the corpora (named knowledge bases, persisted) and delegates ranking to the
chosen backend, so new RAG types drop in by registering a class.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.session import BaseContext


class KnowledgeContext(BaseContext):
    """Context passed into the knowledge manager and backends."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this call.")
    name: str = Field(default="", description="Operation being called.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data.")


class RagBackend(BaseModel):
    """Base class for a retrieval type.

    Stateless by design: the manager persists each knowledge base's corpus and
    hands the full ``texts`` to :meth:`search` on every query, so a backend only
    implements ranking (build-index-then-score is cheap for moderate corpora and
    avoids serializing index structures).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="", description="Registered backend name (e.g. ``bm25``).")
    description: str = Field(default="", description="One-line description of the retrieval type.")

    async def search(self, query: str, texts: List[str], top_k: int) -> List[Tuple[int, float]]:
        """Return ``[(doc_index, score)]`` for the top_k most relevant texts."""
        raise NotImplementedError("All RAG backends must implement search")


__all__ = ["RagBackend", "KnowledgeContext"]
