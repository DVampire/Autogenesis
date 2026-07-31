"""Oracle Vector Store."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class OraclevsTool(VectorStorePluginTool):
    """Oracle Vector Store."""

    name: str = 'oraclevs'
    display_name: str = 'Oracle Vector Store'
    description: str = 'Oracle vector store with search capabilities'
    type: str = 'vectorstore'
    needs_embedding: bool = True

    def _build(self, embedding: Any, **conn: Any) -> Any:
        import oracledb
        from langchain_community.vectorstores.oraclevs import OracleVS
        from langchain_community.vectorstores.utils import DistanceStrategy
        for r in ("user", "password", "dsn"):
            if not conn.get(r):
                raise ValueError(f"Oracle needs '{r}'.")
        client = oracledb.connect(user=conn["user"], password=conn["password"], dsn=conn["dsn"])
        return OracleVS(client=client, embedding_function=embedding,
                        table_name=conn.get("table_name") or "langflow",
                        distance_strategy=DistanceStrategy.DOT_PRODUCT)

    async def __call__(self, user: str = "", password: str = "", dsn: str = "", table_name: str = "langflow", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            user=user, password=password, dsn=dsn, table_name=table_name)
