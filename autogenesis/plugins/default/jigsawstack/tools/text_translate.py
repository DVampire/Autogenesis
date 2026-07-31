"""Text Translate."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackTextTranslateTool(JigsawstackToolBase):
    """Text Translate."""

    name: str = 'text_translate'
    display_name: str = 'Text Translate'
    description: str = 'Translate text from one language to another with support for multiple text formats.'

    async def __call__(self, text: str = "", target_language: str = "en", api_key: str = "", **kwargs) -> Response:
        params = {"text": text, "target_language": target_language}
        return await self._run("translate.text", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
