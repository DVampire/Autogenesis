"""ScrapeGraph Markdownify API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class ScrapegraphMarkdownifyApiTool(PluginTool):
    """ScrapeGraph Markdownify API."""

    name: str = 'scrapegraph_markdownify_api'
    display_name: str = 'ScrapeGraph Markdownify API'
    description: str = 'Given a URL, it will return the markdownified content of the website.'

    async def __call__(self, url: str = "", api_key: str = "", query: str = "", prompt: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "SGAI_API_KEY", "SCRAPEGRAPH_API_KEY")
        if not key:
            return self._fail("scrapegraph.markdownify: no API key (set api_key / SGAI_API_KEY).")
        if not str(url or query or "").strip():
            return self._fail("scrapegraph.markdownify: 'url'/'query' is required.")
        try:
            from scrapegraph_py import Client
            client = Client(api_key=key)
            try:
                response = client.markdownify(website_url=url)
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"scrapegraph.markdownify: {type(exc).__name__}: {exc}")
        return self._ok("ScrapeGraph markdownify completed.", result=response)
