"""NextPlaid."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class NextplaidTool(PluginTool):
    """NextPlaid."""

    name: str = 'nextplaid'
    display_name: str = 'NextPlaid'
    description: str = ''

    async def __call__(self, query: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        key = self._secret(api_key, "NEXTPLAID_API_KEY")
        if not query or not key:
            return self._fail("nextplaid: 'query' and api_key are required.")
        try:
            resp = httpx.post("https://api.nextplaid.com/v1/query",
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"query": query}, timeout=90.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"nextplaid: {type(exc).__name__}: {exc}")
        return self._ok("NextPlaid query completed.", result=data)
