"""Chroma DB."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class ChromaTool(VectorStorePluginTool):
    """Chroma DB."""

    name: str = 'chroma'
    display_name: str = 'Chroma DB'
    description: str = 'Chroma Vector Store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_chroma import Chroma
        client = None
        if conn.get("server_host"):
            from chromadb import HttpClient
            client = HttpClient(host=conn["server_host"], port=int(conn.get("server_port") or 8000))
        return Chroma(collection_name=conn.get("collection_name") or "langflow",
                      persist_directory=conn.get("persist_directory") or None,
                      client=client, embedding_function=embedding)

    async def __call__(self, collection_name: str = "langflow", persist_directory: str = "", server_host: str = "", server_port: int = 8000, query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_name=collection_name, persist_directory=persist_directory,
            server_host=server_host, server_port=int(server_port))
