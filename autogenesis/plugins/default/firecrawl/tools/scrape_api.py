"""Firecrawl Scrape API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class FirecrawlScrapeApiTool(PluginTool):
    """Firecrawl Scrape API."""

    name: str = 'firecrawl_scrape_api'
    display_name: str = 'Firecrawl Scrape API'
    description: str = 'Scrapes a URL and returns the results.'

    async def __call__(self, url: str = "", api_key: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "FIRECRAWL_API_KEY")
        if not key:
            return self._fail("firecrawl.scrape: no API key (set api_key / FIRECRAWL_API_KEY).")
        if not str(url or "").strip():
            return self._fail("firecrawl.scrape: 'url' is required.")
        try:
            from firecrawl import Firecrawl
            app = Firecrawl(api_key=key)
            result = app.scrape(url, formats=['markdown'], only_main_content=True)
            data = result.model_dump() if hasattr(result, "model_dump") else result
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"firecrawl.scrape: {type(exc).__name__}: {exc}")
        return self._ok("Firecrawl scrape completed.", result=data)
