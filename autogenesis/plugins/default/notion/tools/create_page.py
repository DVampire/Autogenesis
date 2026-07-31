"""Create Page ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionCreatePageTool(NotionToolBase):
    """Create Page ."""

    name: str = 'create_page'
    display_name: str = 'Create Page '
    description: str = 'A component for creating Notion pages.'

    async def __call__(self, api_key: str = "", database_id: str = "", properties_json: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            import json as _json
            if not database_id or not properties_json:
                return self._fail("notion.create_page: 'database_id' and 'properties_json' are required.")
            payload = {"parent": {"database_id": database_id}, "properties": _json.loads(properties_json)}
            js = self._request("POST", "/pages", token, json=payload)
            return self._ok(f"Created Notion page {js.get('id')}.", page=js)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.create_page: {type(exc).__name__}: {exc}")
