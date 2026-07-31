"""Astra DB."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class DatastaxAstradbVectorstoreTool(VectorStorePluginTool):
    """Astra DB."""

    name: str = 'astradb_vectorstore'
    display_name: str = 'Astra DB'
    description: str = 'Ingest and search documents in Astra DB'
    type: str = 'vectorstore'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_astradb import AstraDBVectorStore
        token = self._secret(conn.get("token"), "ASTRA_DB_APPLICATION_TOKEN")
        endpoint = conn.get("api_endpoint") or self._secret("", "ASTRA_DB_API_ENDPOINT")
        if not token or not endpoint:
            raise ValueError("Astra DB needs a token (ASTRA_DB_APPLICATION_TOKEN) and api_endpoint.")
        return AstraDBVectorStore(collection_name=conn.get("collection_name") or "langflow",
                                  embedding=embedding, token=token, api_endpoint=endpoint,
                                  namespace=conn.get("namespace") or None)

    async def __call__(self, collection_name: str = "langflow", token: str = "", api_endpoint: str = "", namespace: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_name=collection_name, token=token, api_endpoint=api_endpoint, namespace=namespace)
