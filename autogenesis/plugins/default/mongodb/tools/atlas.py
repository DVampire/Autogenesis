"""MongoDB Atlas."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class MongodbAtlasTool(VectorStorePluginTool):
    """MongoDB Atlas."""

    name: str = 'mongodb_atlas'
    display_name: str = 'MongoDB Atlas'
    description: str = 'MongoDB Atlas Vector Store with search capabilities'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from pymongo import MongoClient
        from langchain_mongodb import MongoDBAtlasVectorSearch
        for req in ("connection_string", "database_name", "collection_name"):
            if not conn.get(req):
                raise ValueError(f"MongoDB Atlas needs '{req}'.")
        client = MongoClient(conn["connection_string"])
        collection = client[conn["database_name"]][conn["collection_name"]]
        return MongoDBAtlasVectorSearch(collection=collection, embedding=embedding,
                                        index_name=conn.get("index_name") or "vector_index")

    async def __call__(self, connection_string: str = "", database_name: str = "", collection_name: str = "", index_name: str = "vector_index", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            connection_string=connection_string, database_name=database_name,
            collection_name=collection_name, index_name=index_name)
