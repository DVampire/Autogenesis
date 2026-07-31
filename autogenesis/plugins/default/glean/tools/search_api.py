"""Glean Search API."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GleanSearchApiTool(PluginTool):
    """Glean Search API."""

    name: str = 'glean_search_api'
    display_name: str = 'Glean Search API'
    description: str = 'Search using Glean'

    async def __call__(self, query: str = "", glean_api_url: str = "", glean_access_token: str = "", page_size: int = 10, **kwargs) -> Response:
        import httpx
        query = str(query or "").strip()
        api_url = str(glean_api_url or "").strip()
        token = self._secret(glean_access_token, "GLEAN_ACCESS_TOKEN")
        if not query or not api_url or not token:
            return self._fail("glean.search: 'query', 'glean_api_url' and access token are required.")
        if not api_url.endswith("/"):
            api_url += "/"
        try:
            resp = httpx.post(
                api_url + "search",
                headers={"Authorization": f"Bearer {token}",
                         "X-Scio-ActAs": "autogenesis@provider"},
                json={"query": query, "pageSize": int(page_size)}, timeout=60.0)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"glean.search: {type(exc).__name__}: {exc}")
        return self._ok(f"Glean returned {len(results)} results for '{query}'.",
                        query=query, records=results, count=len(results))
