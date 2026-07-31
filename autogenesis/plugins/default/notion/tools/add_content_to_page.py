"""Add Content to Page ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionAddContentToPageTool(NotionToolBase):
    """Add Content to Page ."""

    name: str = 'add_content_to_page'
    display_name: str = 'Add Content to Page '
    description: str = 'Convert markdown text to Notion blocks and append them to a Notion page.'

    async def __call__(self, api_key: str = "", page_id: str = "", content_json: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            import json as _json
            if not page_id or not content_json:
                return self._fail("notion.add_content: 'page_id' and 'content_json' (blocks) are required.")
            children = _json.loads(content_json)
            js = self._request("PATCH", f"/blocks/{page_id}/children", token,
                               json={"children": children if isinstance(children, list) else [children]})
            return self._ok(f"Added content to page {page_id}.", result=js)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.add_content_to_page: {type(exc).__name__}: {exc}")
