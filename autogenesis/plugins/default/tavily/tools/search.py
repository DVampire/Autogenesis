"""Tavily web search."""

from autogenesis.plugins.types import PluginTool
from autogenesis.response.types import Response


class TavilySearchTool(PluginTool):
    """Search the web and return ranked results."""

    name: str = "tavily_search"
    display_name: str = "Tavily Search"
    description: str = "Search the web and return ranked results, optionally with a synthesised answer."

    async def __call__(self, query: str = "", api_key: str = "", search_depth: str = "basic",
                       topic: str = "general", max_results: int = 5, include_answer: bool = True,
                       include_raw_content: bool = False, **kwargs) -> Response:
        query = str(query or "").strip()
        if not query:
            return self._fail(f"{self.id}: 'query' is required.")
        key = self._secret(api_key, "TAVILY_API_KEY")
        if not key:
            return self._fail(f"{self.id}: no API key (set api_key or TAVILY_API_KEY).")
        try:
            # Search authenticates in the body, unlike extract's bearer header.
            body = await self.owner.post("/search", {
                "api_key": key, "query": query, "search_depth": search_depth, "topic": topic,
                "max_results": int(max_results), "include_answer": include_answer,
                "include_raw_content": include_raw_content,
            })
        except Exception as exc:  # noqa: BLE001 — network / auth / quota
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        records = [{"title": r.get("title"), "url": r.get("url"),
                    "content": r.get("content", ""), "score": r.get("score")}
                   for r in body.get("results", [])]
        return self._ok(f"Tavily returned {len(records)} result(s) for '{query}'.",
                        query=query, answer=body.get("answer"), records=records, count=len(records))
