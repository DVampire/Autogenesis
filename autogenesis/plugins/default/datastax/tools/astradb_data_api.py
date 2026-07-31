"""Astra DB Data API."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DatastaxAstradbDataApiTool(PluginTool):
    """Astra DB Data API."""

    name: str = 'astradb_data_api'
    display_name: str = 'Astra DB Data API'
    description: str = ''

    async def __call__(self, collection_name: str = "", token: str = "", api_endpoint: str = "", filter: Optional[dict] = None, limit: int = 20, **kwargs) -> Response:
        token = self._secret(token, "ASTRA_DB_APPLICATION_TOKEN")
        endpoint = api_endpoint or self._secret("", "ASTRA_DB_API_ENDPOINT")
        if not collection_name or not token or not endpoint:
            return self._fail("datastax.data_api: 'collection_name', token and api_endpoint are required.")
        try:
            from astrapy import DataAPIClient
            db = DataAPIClient(token).get_database(endpoint)
            docs = list(db.get_collection(collection_name).find(filter or {}, limit=int(limit)))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"datastax.data_api: {type(exc).__name__}: {exc}")
        return self._ok(f"Found {len(docs)} documents.", records=docs, count=len(docs))
