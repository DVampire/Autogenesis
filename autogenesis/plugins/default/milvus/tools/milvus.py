"""Milvus."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class MilvusTool(VectorStorePluginTool):
    """Milvus."""

    name: str = 'milvus'
    display_name: str = 'Milvus'
    description: str = 'Milvus vector store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_milvus.vectorstores import Milvus as LCMilvus
        if not conn.get("uri"):
            raise ValueError("Milvus needs a 'uri' (e.g. http://localhost:19530 or a .db path).")
        args = {"uri": conn["uri"]}
        if conn.get("password"):
            args["token"] = conn["password"]
        return LCMilvus(embedding_function=embedding,
                        collection_name=conn.get("collection_name") or "langflow",
                        connection_args=args, auto_id=True)

    async def __call__(self, collection_name: str = "langflow", uri: str = "", password: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_name=collection_name, uri=uri, password=password)
