"""Object Detection."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackObjectDetectionTool(JigsawstackToolBase):
    """Object Detection."""

    name: str = 'object_detection'
    display_name: str = 'Object Detection'
    description: str = 'Perform object detection on images using JigsawStack'

    async def __call__(self, url: str = "", prompts: list = None, api_key: str = "", **kwargs) -> Response:
        params = {"url": url, "prompts": prompts or []}
        return await self._run("vision.object_detection", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
