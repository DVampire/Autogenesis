"""ScrapeGraph Smart Scraper API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class ScrapegraphSmartScraperApiTool(PluginTool):
    """ScrapeGraph Smart Scraper API."""

    name: str = 'scrapegraph_smart_scraper_api'
    display_name: str = 'ScrapeGraph Smart Scraper API'
    description: str = 'Given a URL, it will return the structured data of the website.'

    async def __call__(self, url: str = "", prompt: str = "", api_key: str = "", query: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "SGAI_API_KEY", "SCRAPEGRAPH_API_KEY")
        if not key:
            return self._fail("scrapegraph.smartscraper: no API key (set api_key / SGAI_API_KEY).")
        if not str(url or query or "").strip():
            return self._fail("scrapegraph.smartscraper: 'url'/'query' is required.")
        if not str(prompt or "").strip():
            return self._fail("scrapegraph.smartscraper: 'prompt' is required.")
        try:
            from scrapegraph_py import Client
            client = Client(api_key=key)
            try:
                response = client.smartscraper(website_url=url, user_prompt=prompt)
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"scrapegraph.smartscraper: {type(exc).__name__}: {exc}")
        return self._ok("ScrapeGraph smartscraper completed.", result=response)
