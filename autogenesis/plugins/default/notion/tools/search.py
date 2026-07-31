"""Search ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionSearchTool(NotionToolBase):
    """Search ."""

    name: str = 'search'
    display_name: str = 'Search '
    description: str = 'Searches all pages and databases that have been shared with an integration.'

    async def __call__(self, api_key: str = "", query: str = "", filter_type: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            data = {"query": query}
            if filter_type:
                data["filter"] = {"value": filter_type, "property": "object"}
            js = self._request("POST", "/search", token, json=data)
            results = js.get("results", [])
            return self._ok(f"Notion search returned {len(results)} objects.",
                            query=query, records=results, count=len(results))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.search: {type(exc).__name__}: {exc}")
