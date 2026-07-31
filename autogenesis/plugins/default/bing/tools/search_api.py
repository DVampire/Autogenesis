"""Bing Search API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class BingSearchApiTool(PluginTool):
    """Bing Search API."""

    name: str = 'bing_search_api'
    display_name: str = 'Bing Search API'
    description: str = 'Call the Bing Search API.'

    async def __call__(self, input_value: str = "", bing_subscription_key: str = "", bing_search_url: str = "", k: int = 4, **kwargs) -> Response:
        query = str(input_value or "").strip()
        if not query:
            return self._fail("bing.search: 'input_value' is required.")
        key = self._secret(bing_subscription_key, "BING_SUBSCRIPTION_KEY", "BING_API_KEY")
        if not key:
            return self._fail("bing.search: no key (set bing_subscription_key / BING_SUBSCRIPTION_KEY).")
        try:
            from langchain_community.utilities import BingSearchAPIWrapper
            kw = {"bing_subscription_key": key}
            if bing_search_url:
                kw["bing_search_url"] = bing_search_url
            wrapper = BingSearchAPIWrapper(**kw)
            results = wrapper.results(query=query, num_results=int(k))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"bing.search: {type(exc).__name__}: {exc}")
        records = [{"title": r.get("title"), "link": r.get("link"), "snippet": r.get("snippet", "")} for r in results]
        return self._ok(f"Bing returned {len(records)} results for '{query}'.",
                        query=query, records=records, count=len(records))
