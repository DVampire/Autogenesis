"""Valkey."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class ValkeyTool(VectorStorePluginTool):
    """Valkey."""

    name: str = 'valkey'
    display_name: str = 'Valkey'
    description: str = 'Implementation of Vector Store using Valkey'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores.redis import Redis
        return Redis(redis_url=conn.get("valkey_url") or "redis://localhost:6379",
                     index_name=conn.get("index_name") or "langflow", embedding=embedding)

    async def __call__(self, index_name: str = "langflow", valkey_url: str = "redis://localhost:6379", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_name=index_name, valkey_url=valkey_url)
