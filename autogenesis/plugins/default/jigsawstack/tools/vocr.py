"""VOCR."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackVocrTool(JigsawstackToolBase):
    """VOCR."""

    name: str = 'vocr'
    display_name: str = 'VOCR'
    description: str = 'Extract data from any document type in a consistent structure with fine-tuned \\\\\\\\\\\\n        vLLMs for the highest accuracy'

    async def __call__(self, url: str = "", prompts: list = None, api_key: str = "", **kwargs) -> Response:
        params = {"url": url, "prompts": prompts or []}
        return await self._run("vision.vocr", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
