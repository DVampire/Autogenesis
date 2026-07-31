"""Page Content Viewer ."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.default.notion._base import NotionToolBase


class NotionPageContentViewerTool(NotionToolBase):
    """Page Content Viewer ."""

    name: str = 'page_content_viewer'
    display_name: str = 'Page Content Viewer '
    description: str = 'Retrieve the content of a Notion page as plain text.'

    async def __call__(self, api_key: str = "", page_id: str = "", **kwargs) -> Response:
        err = self._need_token(api_key)
        if err:
            return err
        token = self._token(api_key)
        try:
            if not page_id:
                return self._fail("notion.page_content_viewer: 'page_id' is required.")
            js = self._request("GET", f"/blocks/{page_id}/children?page_size=100", token)
            blocks = js.get("results", [])
            return self._ok(f"Page {page_id} has {len(blocks)} blocks.", records=blocks, count=len(blocks))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notion.page_content_viewer: {type(exc).__name__}: {exc}")
