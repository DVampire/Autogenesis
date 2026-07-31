"""Google Drive Loader."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GoogleDriveTool(PluginTool):
    """Google Drive Loader."""

    name: str = 'google_drive'
    display_name: str = 'Google Drive Loader'
    description: str = 'Loads documents from Google Drive using provided credentials.'

    async def __call__(self, document_ids: str = "", credentials_json: str = "", **kwargs) -> Response:
        ids = [i.strip() for i in str(document_ids or "").split(",") if i.strip()]
        if not ids:
            return self._fail("google.drive: 'document_ids' (comma-separated) is required.")
        try:
            from langchain_google_community import GoogleDriveLoader
            docs = GoogleDriveLoader(document_ids=ids).load()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"google.drive: {type(exc).__name__}: {exc}")
        records = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
        return self._ok(f"Loaded {len(records)} Drive documents.", records=records, count=len(records))
