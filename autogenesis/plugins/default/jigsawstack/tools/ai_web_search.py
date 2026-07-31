"""AI Web Search."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackAiWebSearchTool(JigsawstackToolBase):
    """AI Web Search."""

    name: str = 'ai_web_search'
    display_name: str = 'AI Web Search'
    description: str = 'Effortlessly search the Web and get access to high-quality results powered with AI.'

    async def __call__(self, query: str = "", ai_overview: bool = True, safe_search: str = "moderate", api_key: str = "", **kwargs) -> Response:
        params = {"query": query, "ai_overview": ai_overview, "safe_search": safe_search}
        return await self._run("web.search", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
