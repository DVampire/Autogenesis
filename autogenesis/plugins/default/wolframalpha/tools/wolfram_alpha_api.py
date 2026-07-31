"""WolframAlpha API."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class WolframalphaWolframAlphaApiTool(PluginTool):
    """WolframAlpha API."""

    name: str = 'wolfram_alpha_api'
    display_name: str = 'WolframAlpha API'
    description: str = 'WolframAlpha API'

    async def __call__(self, input_value: str = "", app_id: str = "", **kwargs) -> Response:
        q = str(input_value or "").strip()
        key = self._secret(app_id, "WOLFRAM_ALPHA_APPID")
        if not q or not key:
            return self._fail("wolframalpha: 'input_value' and app_id (WOLFRAM_ALPHA_APPID) are required.")
        try:
            from langchain_community.utilities.wolfram_alpha import WolframAlphaAPIWrapper
            out = WolframAlphaAPIWrapper(wolfram_alpha_appid=key).run(q)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"wolframalpha: {type(exc).__name__}: {exc}")
        return self._ok(str(out), query=q, result=str(out))
