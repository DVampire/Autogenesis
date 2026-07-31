"""AI Scraper."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackAiScrapeTool(JigsawstackToolBase):
    """AI Scraper."""

    name: str = 'ai_scrape'
    display_name: str = 'AI Scraper'
    description: str = 'Scrape any website instantly and get consistent structured data \\\\\\\\\\\\n        in seconds without writing any css selector code'

    async def __call__(self, url: str = "", element_prompts: list = None, api_key: str = "", **kwargs) -> Response:
        params = {"url": url, "element_prompts": element_prompts or []}
        return await self._run("web.ai_scrape", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
