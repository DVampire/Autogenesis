"""Pinecone."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class PineconeTool(VectorStorePluginTool):
    """Pinecone."""

    name: str = 'pinecone'
    display_name: str = 'Pinecone'
    description: str = 'Pinecone Vector Store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_pinecone import PineconeVectorStore
        key = self._secret(conn.get("pinecone_api_key"), "PINECONE_API_KEY")
        if not conn.get("index_name") or not key:
            raise ValueError("Pinecone needs 'index_name' and an API key (PINECONE_API_KEY).")
        return PineconeVectorStore(index_name=conn["index_name"], embedding=embedding,
                                   text_key=conn.get("text_key") or "text",
                                   namespace=conn.get("namespace") or None, pinecone_api_key=key)

    async def __call__(self, index_name: str = "", pinecone_api_key: str = "", namespace: str = "", text_key: str = "text", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_name=index_name, pinecone_api_key=pinecone_api_key,
            namespace=namespace, text_key=text_key)
