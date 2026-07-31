"""Astra DB CQL."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DatastaxAstradbCqlTool(PluginTool):
    """Astra DB CQL."""

    name: str = 'astradb_cql'
    display_name: str = 'Astra DB CQL'
    description: str = 'Create a tool to get transactional data from DataStax Astra DB CQL Table'

    async def __call__(self, keyspace: str = "", query: str = "", token: str = "", api_endpoint: str = "", **kwargs) -> Response:
        token = self._secret(token, "ASTRA_DB_APPLICATION_TOKEN")
        if not query or not token:
            return self._fail("datastax.cql: 'query' and a token are required.")
        try:
            import cassio
            cassio.init(token=token, database_id=api_endpoint or self._secret("", "ASTRA_DB_ID"))
            session = cassio.config.resolve_session()
            rows = [dict(r._asdict()) for r in session.execute(query)]
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"datastax.cql: {type(exc).__name__}: {exc}")
        return self._ok(f"CQL returned {len(rows)} rows.", records=rows, count=len(rows))
