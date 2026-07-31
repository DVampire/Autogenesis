"""SearchApi."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class SearchapiSearchTool(PluginTool):
    """SearchApi."""

    name: str = 'search'
    display_name: str = 'SearchApi'
    description: str = 'Calls the SearchApi API with result limiting. Supports Google, Bing and DuckDuckGo.'

    async def __call__(self, input_value: str = "", api_key: str = "", engine: str = "google", max_results: int = 5, max_snippet_length: int = 100, **kwargs) -> Response:
        query = str(input_value or "").strip()
        if not query:
            return self._fail("searchapi.search: 'input_value' is required.")
        key = self._secret(api_key, "SEARCHAPI_API_KEY")
        if not key:
            return self._fail("searchapi.search: no API key (set api_key / SEARCHAPI_API_KEY).")
        try:
            from langchain_community.utilities.searchapi import SearchApiAPIWrapper
            wrapper = SearchApiAPIWrapper(engine=engine, searchapi_api_key=key)
            full = wrapper.results(query=query)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"searchapi.search: {type(exc).__name__}: {exc}")
        organic = (full or {}).get("organic_results", [])[: int(max_results)]
        records = [{"title": r.get("title", "")[: int(max_snippet_length)], "link": r.get("link", ""),
                    "snippet": r.get("snippet", "")[: int(max_snippet_length)]} for r in organic]
        return self._ok(f"SearchApi returned {len(records)} results for '{query}'.",
                        query=query, records=records, count=len(records))
