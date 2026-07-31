"""LangWatch Evaluator."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class LangwatchTool(PluginTool):
    """LangWatch Evaluator."""

    name: str = 'langwatch'
    display_name: str = 'LangWatch Evaluator'
    description: str = 'Evaluates various aspects of language models using LangWatch'

    async def __call__(self, evaluator: str = "", input_value: str = "", output_value: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        key = self._secret(api_key, "LANGWATCH_API_KEY")
        if not evaluator or not key:
            return self._fail("langwatch: 'evaluator' and api_key (LANGWATCH_API_KEY) are required.")
        try:
            resp = httpx.post(f"https://app.langwatch.ai/api/evaluations/{evaluator}/evaluate",
                              headers={"X-Auth-Token": key, "Content-Type": "application/json"},
                              json={"data": {"input": input_value, "output": output_value}}, timeout=60.0)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"langwatch: {type(exc).__name__}: {exc}")
        return self._ok("LangWatch evaluation completed.", result=result)
