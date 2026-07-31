"""List Users ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionListUsersTool(NotionToolBase):
    """List Users ."""

    name: str = 'list_users'
    display_name: str = 'List Users '
    description: str = 'Retrieve users from Notion.'

    async def __call__(self, api_key: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            js = self._request("GET", "/users", token)
            results = js.get("results", [])
            return self._ok(f"Notion has {len(results)} users.", records=results, count=len(results))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.list_users: {type(exc).__name__}: {exc}")
