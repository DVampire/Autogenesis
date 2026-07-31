"""Built-in RAG retrieval types.

- ``bm25``: sparse lexical ranking (rank_bm25) — good for keyword overlap.
- ``tfidf``: TF-IDF vectors + cosine similarity (scikit-learn).

Both are pure/offline (no embedding model, no network). An ``embedding`` type
that calls model_manager can be added the same way when a model is configured.
"""

from typing import List, Tuple

from autogenesis.registry import KNOWLEDGE
from autogenesis.knowledge.types import RagBackend


@KNOWLEDGE.register_module(force=True)
class BM25Knowledge(RagBackend):
    """Sparse lexical retrieval (Okapi BM25)."""

    name: str = "bm25"
    description: str = "BM25 sparse lexical retrieval (keyword overlap)."

    async def search(self, query: str, texts: List[str], top_k: int) -> List[Tuple[int, float]]:
        from rank_bm25 import BM25Okapi

        if not texts:
            return []
        tokenized = [str(text).lower().split() for text in texts]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(str(query).lower().split())
        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return [(index, float(score)) for index, score in ranked[:max(1, top_k)]]


@KNOWLEDGE.register_module(force=True)
class TfidfKnowledge(RagBackend):
    """TF-IDF vector retrieval with cosine similarity."""

    name: str = "tfidf"
    description: str = "TF-IDF vectors with cosine similarity."

    async def search(self, query: str, texts: List[str], top_k: int) -> List[Tuple[int, float]]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        if not texts:
            return []
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform([str(text) for text in texts])
        query_vector = vectorizer.transform([str(query)])
        sims = cosine_similarity(query_vector, matrix)[0]
        ranked = sorted(enumerate(sims), key=lambda pair: pair[1], reverse=True)
        return [(index, float(score)) for index, score in ranked[:max(1, top_k)]]
