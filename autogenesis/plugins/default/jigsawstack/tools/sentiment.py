"""Sentiment Analysis."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackSentimentTool(JigsawstackToolBase):
    """Sentiment Analysis."""

    name: str = 'sentiment'
    display_name: str = 'Sentiment Analysis'
    description: str = 'Analyze sentiment of text using JigsawStack AI'

    async def __call__(self, text: str = "", api_key: str = "", **kwargs) -> Response:
        params = {"text": text}
        return await self._run("sentiment", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
