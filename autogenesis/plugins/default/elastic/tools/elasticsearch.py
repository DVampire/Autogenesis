"""Elasticsearch."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class ElasticsearchTool(VectorStorePluginTool):
    """Elasticsearch."""

    name: str = 'elasticsearch'
    display_name: str = 'Elasticsearch'
    description: str = 'Elasticsearch Vector Store with with advanced, customizable search capabilities.'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_elasticsearch import ElasticsearchStore
        p = {"index_name": conn.get("index_name") or "langflow", "embedding": embedding,
             "es_user": conn.get("username") or None, "es_password": conn.get("password") or None}
        if conn.get("cloud_id"):
            p["es_cloud_id"] = conn["cloud_id"]
        elif conn.get("elasticsearch_url"):
            p["es_url"] = conn["elasticsearch_url"]
        else:
            raise ValueError("Elasticsearch needs 'elasticsearch_url' or 'cloud_id'.")
        return ElasticsearchStore(**p)

    async def __call__(self, index_name: str = "langflow", elasticsearch_url: str = "", cloud_id: str = "", username: str = "", password: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_name=index_name, elasticsearch_url=elasticsearch_url, cloud_id=cloud_id,
            username=username, password=password)
