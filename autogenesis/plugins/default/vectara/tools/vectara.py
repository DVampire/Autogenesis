"""Vectara."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class VectaraTool(VectorStorePluginTool):
    """Vectara."""

    name: str = 'vectara'
    display_name: str = 'Vectara'
    description: str = 'Vectara Vector Store with search capabilities'
    needs_embedding: bool = False

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import Vectara
        key = self._secret(conn.get("vectara_api_key"), "VECTARA_API_KEY")
        if not conn.get("vectara_customer_id") or not conn.get("vectara_corpus_id") or not key:
            raise ValueError("Vectara needs customer_id, corpus_id and an API key (VECTARA_API_KEY).")
        return Vectara(vectara_customer_id=conn["vectara_customer_id"],
                       vectara_corpus_id=conn["vectara_corpus_id"], vectara_api_key=key)

    async def __call__(self, vectara_customer_id: str = "", vectara_corpus_id: str = "", vectara_api_key: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            vectara_customer_id=vectara_customer_id, vectara_corpus_id=vectara_corpus_id,
            vectara_api_key=vectara_api_key)
