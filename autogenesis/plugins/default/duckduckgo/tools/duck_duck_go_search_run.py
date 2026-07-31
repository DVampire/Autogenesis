"""DuckDuckGo Search."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DuckduckgoDuckDuckGoSearchRunTool(PluginTool):
    """DuckDuckGo Search."""

    name: str = 'duck_duck_go_search_run'
    display_name: str = 'DuckDuckGo Search'
    description: str = 'Search the web using DuckDuckGo with customizable result limits'

    async def __call__(self, input_value: str = "", max_results: int = 5, max_snippet_length: int = 100, **kwargs) -> Response:
        query = str(input_value or "").strip()
        if not query:
            return self._fail("duckduckgo.search: 'input_value' is required.")
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            wrapper = DuckDuckGoSearchRun()
            full = wrapper.run(f"{query} (site:*)")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"duckduckgo.search: {type(exc).__name__}: {exc}")
        lines = [ln for ln in full.split("\n") if ln.strip()][: int(max_results)]
        records = [{"content": ln, "snippet": ln[: int(max_snippet_length)]} for ln in lines]
        return self._ok(f"DuckDuckGo returned {len(records)} results for '{query}'.",
                        query=query, records=records, count=len(records))
