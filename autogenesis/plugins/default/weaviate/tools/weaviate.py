"""Weaviate."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class WeaviateTool(VectorStorePluginTool):
    """Weaviate."""

    name: str = 'weaviate'
    display_name: str = 'Weaviate'
    description: str = 'Weaviate Vector Store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        import weaviate as weaviate_client
        from langchain_weaviate import WeaviateVectorStore
        idx = conn.get("index_name") or ""
        if not idx:
            raise ValueError("Weaviate needs an 'index_name'.")
        if idx != idx.capitalize():
            raise ValueError(f"Weaviate index name must be capitalized: {idx.capitalize()}")
        auth = None
        if conn.get("api_key"):
            from weaviate.classes.init import Auth
            auth = Auth.api_key(conn["api_key"])
        client = weaviate_client.connect_to_custom(http_host=conn.get("url") or "localhost",
                                                   http_port=8080, http_secure=False,
                                                   grpc_host=conn.get("url") or "localhost",
                                                   grpc_port=50051, grpc_secure=False,
                                                   auth_credentials=auth)
        return WeaviateVectorStore(client=client, index_name=idx,
                                   text_key=conn.get("text_key") or "text", embedding=embedding)

    async def __call__(self, index_name: str = "", url: str = "", api_key: str = "", text_key: str = "text", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_name=index_name, url=url, api_key=api_key, text_key=text_key)
