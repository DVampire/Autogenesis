"""Google Drive Search."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GoogleDriveSearchTool(PluginTool):
    """Google Drive Search."""

    name: str = 'google_drive_search'
    display_name: str = 'Google Drive Search'
    description: str = 'Searches Google Drive files using provided credentials and query parameters.'

    async def __call__(self, query: str = "", credentials_json: str = "", **kwargs) -> Response:
        return self._fail("google.drive_search: requires Google OAuth credentials (credentials_json) "
                          "and the Drive API; configure a service account or OAuth token to use.")
