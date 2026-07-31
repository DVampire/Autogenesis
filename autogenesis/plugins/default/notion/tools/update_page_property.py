"""Update Page Property ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionUpdatePagePropertyTool(NotionToolBase):
    """Update Page Property ."""

    name: str = 'update_page_property'
    display_name: str = 'Update Page Property '
    description: str = 'Update the properties of a Notion page.'

    async def __call__(self, api_key: str = "", page_id: str = "", properties_json: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            import json as _json
            if not page_id or not properties_json:
                return self._fail("notion.update_page_property: 'page_id' and 'properties_json' are required.")
            js = self._request("PATCH", f"/pages/{page_id}", token,
                               json={"properties": _json.loads(properties_json)})
            return self._ok(f"Updated page {page_id}.", page=js)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.update_page_property: {type(exc).__name__}: {exc}")
