"""Needle Retriever."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class NeedleTool(VectorStorePluginTool):
    """Needle Retriever."""

    name: str = 'needle'
    display_name: str = 'Needle Retriever'
    description: str = 'A retriever that uses the Needle API to search collections.'
    needs_embedding: bool = False

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import NeedleVectorStore
        key = self._secret(conn.get("needle_api_key"), "NEEDLE_API_KEY")
        if not conn.get("collection_id") or not key:
            raise ValueError("Needle needs 'collection_id' and an API key (NEEDLE_API_KEY).")
        return NeedleVectorStore(needle_api_key=key, collection_id=conn["collection_id"])

    async def __call__(self, collection_id: str = "", needle_api_key: str = "", top_k: int = 5, query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_id=collection_id, needle_api_key=needle_api_key)
