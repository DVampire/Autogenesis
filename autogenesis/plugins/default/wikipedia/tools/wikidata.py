"""Wikidata."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class WikipediaWikidataTool(PluginTool):
    """Wikidata."""

    name: str = 'wikidata'
    display_name: str = 'Wikidata'
    description: str = 'Performs a search using the Wikidata API.'

    async def __call__(self, query: str = "", **kwargs) -> Response:
        import httpx
        query = str(query or "").strip()
        if not query:
            return self._fail("wikipedia.wikidata: 'query' is required.")
        try:
            resp = httpx.get("https://www.wikidata.org/w/api.php",
                             params={"action": "wbsearchentities", "format": "json", "search": query, "language": "en"},
                             headers={"User-Agent": "Autogenesis/1.0 (provider plugin; +https://autogenesis)"},
                             timeout=30.0)
            resp.raise_for_status()
            results = resp.json().get("search", [])
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"wikipedia.wikidata: {type(exc).__name__}: {exc}")
        records = [{"label": r.get("label"), "id": r.get("id"), "url": r.get("url"),
                    "description": r.get("description", ""), "concepturi": r.get("concepturi")} for r in results]
        return self._ok(f"Wikidata returned {len(records)} entities for '{query}'.",
                        query=query, records=records, count=len(records))
