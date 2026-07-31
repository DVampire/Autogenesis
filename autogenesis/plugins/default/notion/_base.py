"""Shared base for the Notion provider tools (ported from Langflow).

All Notion components call ``api.notion.com`` with an integration token and the
``Notion-Version`` header. The token resolves from the call arg, the
``notion_plugin`` config block, or ``NOTION_API_KEY`` / ``NOTION_TOKEN``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool

NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"


class NotionToolBase(PluginTool):
    """Base for Notion tools — token resolution + a REST helper."""

    category: str = "data"

    def _token(self, arg: str = "") -> str:
        return self._secret(arg, "NOTION_API_KEY", "NOTION_TOKEN", "NOTION_INTEGRATION_TOKEN")

    def _request(self, method: str, path: str, token: str,
                 json: Optional[Dict[str, Any]] = None) -> Any:
        import httpx

        headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION,
                   "Content-Type": "application/json"}
        resp = httpx.request(method, f"{BASE}{path}", headers=headers, json=json, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    def _need_token(self, arg: str) -> Optional[Response]:
        if not self._token(arg):
            return self._fail(f"{self.name}: no Notion token (set api_key / NOTION_API_KEY).")
        return None
