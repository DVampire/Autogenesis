"""Google Serper API."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GoogleSerperApiCoreTool(PluginTool):
    """Google Serper API."""

    name: str = 'google_serper_api_core'
    display_name: str = 'Google Serper API'
    description: str = 'Call the Serper.dev Google Search API.'

    async def __call__(self, input_value: str = "", serper_api_key: str = "", k: int = 4, **kwargs) -> Response:
        q = str(input_value or "").strip()
        key = self._secret(serper_api_key, "SERPER_API_KEY")
        if not q or not key:
            return self._fail("google.serper: needs input_value and SERPER_API_KEY.")
        try:
            from langchain_community.utilities import GoogleSerperAPIWrapper
            results = GoogleSerperAPIWrapper(serper_api_key=key, k=int(k)).results(q)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"google.serper: {type(exc).__name__}: {exc}")
        organic = (results or {}).get("organic", [])
        return self._ok(f"Serper returned {len(organic)} results.", query=q, records=organic, count=len(organic))
