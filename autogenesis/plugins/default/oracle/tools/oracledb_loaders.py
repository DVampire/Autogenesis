"""Oracle Doc Loader."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class OracledbLoadersTool(PluginTool):
    """Oracle Doc Loader."""

    name: str = 'oracledb_loaders'
    display_name: str = 'Oracle Doc Loader'
    description: str = 'Read documents from Oracle Database using OracleDocLoader.'
    category: str = 'data'
    type: str = 'tool'

    async def __call__(self, user: str = "", password: str = "", dsn: str = "", query: str = "", **kwargs) -> Response:
        for r in ("user", "password", "dsn"):
            if not locals().get(r):
                return self._fail(f"oracle.loaders: '{r}' is required.")
        try:
            import oracledb
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            cur = conn.cursor()
            cur.execute(query or "SELECT 1 FROM dual")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"oracle.loaders: {type(exc).__name__}: {exc}")
        return self._ok(f"Loaded {len(rows)} rows.", records=rows, count=len(rows))
