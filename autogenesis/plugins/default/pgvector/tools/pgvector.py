"""PGVector."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class PgvectorTool(VectorStorePluginTool):
    """PGVector."""

    name: str = 'pgvector'
    display_name: str = 'PGVector'
    description: str = 'PGVector Vector Store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import PGVector
        if not conn.get("pg_server_url"):
            raise ValueError("PGVector needs 'pg_server_url' (postgresql connection string).")
        return PGVector(embedding_function=embedding,
                        collection_name=conn.get("collection_name") or "langflow",
                        connection_string=conn["pg_server_url"])

    async def __call__(self, collection_name: str = "langflow", pg_server_url: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            collection_name=collection_name, pg_server_url=pg_server_url)
