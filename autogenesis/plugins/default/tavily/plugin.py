"""Tavily — a web search API built for LLM retrieval."""

from typing import Any, ClassVar, Dict, Optional

from pydantic import PrivateAttr

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.extract import TavilyExtractTool
from .tools.search import TavilySearchTool


@PLUGIN.register_module(force=True)
class TavilyPlugin(Plugin):
    """Search the web, and pull the full text out of the pages it finds.

    Both tools hit the same host with the same credential, so the connection
    pool and the key live here rather than being rebuilt on every call.
    """

    tools = (TavilySearchTool, TavilyExtractTool)

    name: str = "tavily"
    display_name: str = "Tavily"
    description: str = "Web search and page extraction, tuned for LLM retrieval."
    category: str = "data"
    type: str = "tool"

    BASE_URL: ClassVar[str] = "https://api.tavily.com"
    #: Long: Tavily's advanced search depth routinely takes tens of seconds.
    TIMEOUT: ClassVar[float] = 90.0

    _client: Optional[Any] = PrivateAttr(default=None)

    def api_key(self, explicit: str = "") -> str:
        """This plugin's credential: call argument → config block → environment."""
        return self.secret(explicit, "TAVILY_API_KEY")

    async def post(self, path: str, payload: Dict[str, Any], *, bearer: str = "") -> Dict[str, Any]:
        """POST JSON to Tavily and return the decoded body.

        Raises on a transport error or a non-2xx status; the calling tool turns
        that into a failed :class:`Response`.
        """
        import httpx

        if self._client is None:
            # Async, so a slow search does not block the event loop the way the
            # per-call synchronous client used to.
            self._client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=self.TIMEOUT)
        headers = {"content-type": "application/json", "accept": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        response = await self._client.post(path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def cleanup(self) -> None:
        """Close the shared connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
