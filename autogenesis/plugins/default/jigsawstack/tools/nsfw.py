"""NSFW Detection."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackNsfwTool(JigsawstackToolBase):
    """NSFW Detection."""

    name: str = 'nsfw'
    display_name: str = 'NSFW Detection'
    description: str = 'Detect if image/video contains NSFW content'

    async def __call__(self, url: str = "", api_key: str = "", **kwargs) -> Response:
        params = {"url": url}
        return await self._run("validate.nsfw", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
