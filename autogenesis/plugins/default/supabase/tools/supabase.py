"""Supabase."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class SupabaseTool(VectorStorePluginTool):
    """Supabase."""

    name: str = 'supabase'
    display_name: str = 'Supabase'
    description: str = 'Supabase Vector Store with search capabilities'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from supabase.client import create_client
        from langchain_community.vectorstores import SupabaseVectorStore
        key = self._secret(conn.get("supabase_service_key"), "SUPABASE_SERVICE_KEY")
        if not conn.get("supabase_url") or not key:
            raise ValueError("Supabase needs 'supabase_url' and a service key (SUPABASE_SERVICE_KEY).")
        client = create_client(conn["supabase_url"], supabase_key=key)
        return SupabaseVectorStore(client=client, embedding=embedding,
                                   table_name=conn.get("table_name") or "documents",
                                   query_name=conn.get("query_name") or "match_documents")

    async def __call__(self, supabase_url: str = "", supabase_service_key: str = "", table_name: str = "documents", query_name: str = "match_documents", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            supabase_url=supabase_url, supabase_service_key=supabase_service_key,
            table_name=table_name, query_name=query_name)
