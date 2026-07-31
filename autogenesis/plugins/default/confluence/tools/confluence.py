"""Confluence."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class ConfluenceTool(PluginTool):
    """Confluence."""

    name: str = 'confluence'
    display_name: str = 'Confluence'
    description: str = 'Confluence wiki collaboration platform'

    async def __call__(self, url: str = "", username: str = "", api_key: str = "", space_key: str = "", cloud: bool = True, max_pages: int = 50, **kwargs) -> Response:
        key = self._secret(api_key, "CONFLUENCE_API_KEY")
        if not url or not username or not key or not space_key:
            return self._fail("confluence: needs url, username, api_key, space_key.")
        try:
            from langchain_community.document_loaders import ConfluenceLoader
            docs = ConfluenceLoader(url=url, username=username, api_key=key, cloud=cloud,
                                    space_key=space_key, max_pages=int(max_pages)).load()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"confluence: {type(exc).__name__}: {exc}")
        records = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
        return self._ok(f"Loaded {len(records)} Confluence pages.", records=records, count=len(records))
