"""OpenSearch (Multi-Model Multi-Embedding)."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class ElasticOpensearchMultimodalTool(VectorStorePluginTool):
    """OpenSearch (Multi-Model Multi-Embedding)."""

    name: str = 'opensearch_multimodal'
    display_name: str = 'OpenSearch (Multi-Model Multi-Embedding)'
    description: str = ''
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import OpenSearchVectorSearch
        auth = (conn["username"], conn.get("password") or "") if conn.get("username") else None
        return OpenSearchVectorSearch(index_name=conn.get("index_name") or "langflow",
                                      embedding_function=embedding,
                                      opensearch_url=conn.get("opensearch_url") or "https://localhost:9200",
                                      http_auth=auth, verify_certs=False)

    async def __call__(self, index_name: str = "langflow", opensearch_url: str = "https://localhost:9200", username: str = "", password: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            index_name=index_name, opensearch_url=opensearch_url, username=username, password=password)
