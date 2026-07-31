"""Couchbase."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class CouchbaseTool(VectorStorePluginTool):
    """Couchbase."""

    name: str = 'couchbase'
    display_name: str = 'Couchbase'
    description: str = 'Couchbase Vector Store with search capabilities'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from datetime import timedelta
        from couchbase.auth import PasswordAuthenticator
        from couchbase.cluster import Cluster
        from couchbase.options import ClusterOptions
        from langchain_couchbase import CouchbaseSearchVectorStore
        for r in ("connection_string", "bucket_name", "scope_name", "collection_name", "index_name"):
            if not conn.get(r):
                raise ValueError(f"Couchbase needs '{r}'.")
        auth = PasswordAuthenticator(conn.get("username") or "", conn.get("password") or "")
        cluster = Cluster(conn["connection_string"], ClusterOptions(auth))
        cluster.wait_until_ready(timedelta(seconds=5))
        return CouchbaseSearchVectorStore(cluster=cluster, bucket_name=conn["bucket_name"],
                                          scope_name=conn["scope_name"], collection_name=conn["collection_name"],
                                          embedding=embedding, index_name=conn["index_name"])

    async def __call__(self, connection_string: str = "", username: str = "", password: str = "", bucket_name: str = "", scope_name: str = "", collection_name: str = "", index_name: str = "", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            connection_string=connection_string, username=username, password=password,
            bucket_name=bucket_name, scope_name=scope_name, collection_name=collection_name, index_name=index_name)
