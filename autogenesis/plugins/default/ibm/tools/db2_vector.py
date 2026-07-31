"""IBM Db2 Vector Store."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class IbmDb2VectorTool(VectorStorePluginTool):
    """IBM Db2 Vector Store."""

    name: str = 'db2_vector'
    display_name: str = 'IBM Db2 Vector Store'
    description: str = ''
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        import ibm_db_dbi
        from langchain_db2 import DB2VS
        if not conn.get("connection_string"):
            raise ValueError("DB2 needs a 'connection_string'.")
        client = ibm_db_dbi.connect(conn["connection_string"], "", "")
        return DB2VS(client=client, embedding_function=embedding,
                     table_name=conn.get("table_name") or "langflow")

    async def __call__(self, connection_string: str = "", table_name: str = "langflow", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            connection_string=connection_string, table_name=table_name)
