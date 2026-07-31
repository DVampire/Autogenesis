"""Google OAuth Token."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GoogleOauthTokenTool(PluginTool):
    """Google OAuth Token."""

    name: str = 'google_oauth_token'
    display_name: str = 'Google OAuth Token'
    description: str = 'Generates a JSON string with your Google OAuth token.'

    async def __call__(self, credentials_json: str = "", scopes: str = "", **kwargs) -> Response:
        return self._fail("google.oauth_token: performs an interactive Google OAuth flow; supply a "
                          "service-account or pre-authorized token JSON (credentials_json) instead.")
