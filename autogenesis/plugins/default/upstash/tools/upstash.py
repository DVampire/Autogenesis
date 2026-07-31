"""Upstash."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class UpstashTool(VectorStorePluginTool):
    """Upstash."""

    name: str = 'upstash'
    display_name: str = 'Upstash'
    description: str = 'Upstash Vector Store with search capabilities'
    needs_embedding: bool = False

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import UpstashVectorStore
        url = conn.get("index_url") or ""
        token = self._secret(conn.get("index_token"), "UPSTASH_VECTOR_REST_TOKEN")
        if not url or not token:
            raise ValueError("Upstash needs 'index_url' and 'index_token'.")
        return UpstashVectorStore(embedding=True, text_key=conn.get("text_key") or "text",
                                  index_url=url, index_token=token,
                                  namespace=conn.get("namespace") or "")

    async def __call__(self, index_url: str = "", index_token: str = "", text_key: str = "text", namespace: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_url=index_url, index_token=index_token, text_key=text_key, namespace=namespace)
