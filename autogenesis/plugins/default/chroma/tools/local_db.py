"""Local DB."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class ChromaLocalDbTool(VectorStorePluginTool):
    """Local DB."""

    name: str = 'local_db'
    display_name: str = 'Local DB'
    description: str = 'Local Vector Store with search capabilities'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_chroma import Chroma
        return Chroma(collection_name=conn.get("collection_name") or "langflow",
                      persist_directory=conn.get("persist_directory") or None,
                      embedding_function=embedding)

    async def __call__(self, collection_name: str = "langflow", persist_directory: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_name=collection_name, persist_directory=persist_directory)
