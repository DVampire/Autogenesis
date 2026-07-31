"""ScrapeGraph Search API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class ScrapegraphSearchApiTool(PluginTool):
    """ScrapeGraph Search API."""

    name: str = 'scrapegraph_search_api'
    display_name: str = 'ScrapeGraph Search API'
    description: str = 'Given a search prompt, it will return search results using ScrapeGraph'

    async def __call__(self, query: str = "", api_key: str = "", url: str = "", prompt: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "SGAI_API_KEY", "SCRAPEGRAPH_API_KEY")
        if not key:
            return self._fail("scrapegraph.searchscraper: no API key (set api_key / SGAI_API_KEY).")
        if not str(url or query or "").strip():
            return self._fail("scrapegraph.searchscraper: 'url'/'query' is required.")
        try:
            from scrapegraph_py import Client
            client = Client(api_key=key)
            try:
                response = client.searchscraper(user_prompt=query)
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"scrapegraph.searchscraper: {type(exc).__name__}: {exc}")
        return self._ok("ScrapeGraph searchscraper completed.", result=response)
