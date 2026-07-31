"""Oracle Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class OracledbEmbeddingsTool(EmbeddingPluginTool):
    """Oracle Embeddings."""

    name: str = 'oracledb_embeddings'
    display_name: str = 'Oracle Embeddings'
    description: str = 'Generate embeddings using Oracle AI Vector Search.'

    def _embeddings(self, **cfg: Any) -> Any:
        import oracledb
        from langchain_community.embeddings.oracleai import OracleEmbeddings
        conn = oracledb.connect(user=cfg.get("user", ""), password=cfg.get("password", ""), dsn=cfg.get("dsn", ""))
        return OracleEmbeddings(conn=conn, params={"provider": "database", "model": cfg.get("model_name")})

    async def __call__(self, text: str = "", model_name: str = "", user: str = "", password: str = "",
                       dsn: str = "", **kwargs) -> Response:
        if not dsn:
            return self._fail("oracle.embeddings: 'dsn', 'user', 'password' are required.")
        return await self._embed(text=text, model_name=model_name, user=user, password=password, dsn=dsn)
