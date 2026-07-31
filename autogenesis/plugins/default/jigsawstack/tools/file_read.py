"""File Read."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackFileReadTool(JigsawstackToolBase):
    """File Read."""

    name: str = 'file_read'
    display_name: str = 'File Read'
    description: str = 'Read any previously uploaded file seamlessly from \\\\\\\\\\\\n        JigsawStack File Storage and use it in your AI applications.'

    async def __call__(self, key: str = "", api_key: str = "", **kwargs) -> Response:
        params = {"key": key}
        return await self._run("store.get", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
