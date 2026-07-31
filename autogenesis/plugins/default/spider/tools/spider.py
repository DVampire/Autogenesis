"""Spider Web Crawler & Scraper."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class SpiderTool(PluginTool):
    """Spider Web Crawler & Scraper."""

    name: str = 'spider'
    display_name: str = 'Spider Web Crawler & Scraper'
    description: str = 'Spider API for web crawling and scraping.'

    async def __call__(self, url: str = "", spider_api_key: str = "", mode: str = "scrape", limit: int = 0, **kwargs) -> Response:
        key = self._secret(spider_api_key, "SPIDER_API_KEY")
        if not key:
            return self._fail("spider: no API key (set spider_api_key / SPIDER_API_KEY).")
        if not str(url or "").strip():
            return self._fail("spider: 'url' is required.")
        if mode not in ("scrape", "crawl"):
            return self._fail("spider: 'mode' must be 'scrape' or 'crawl'.")
        try:
            from spider.spider import Spider
            app = Spider(api_key=key)
            params = {"limit": int(limit) or None, "return_format": "markdown"}
            if mode == "scrape":
                params["limit"] = 1
                result = app.scrape_url(url, params)
            else:
                result = app.crawl_url(url, params)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"spider: {type(exc).__name__}: {exc}")
        records = [{"content": r.get("content"), "url": r.get("url")} for r in (result or [])]
        return self._ok(f"Spider {mode} returned {len(records)} page(s).",
                        records=records, count=len(records))
