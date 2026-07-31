"""Cleanlab Evaluator."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class CleanlabEvaluatorTool(PluginTool):
    """Cleanlab Evaluator."""

    name: str = 'cleanlab_evaluator'
    display_name: str = 'Cleanlab Evaluator'
    description: str = 'Evaluates any LLM response using Cleanlab and outputs trust score and explanation.'

    async def __call__(self, prompt: str = "", response: str = "", api_key: str = "", model: str = "gpt-4o-mini", **kwargs) -> Response:
        key = self._secret(api_key, "CLEANLAB_TLM_API_KEY", "CLEANLAB_API_KEY")
        if not prompt or not response or not key:
            return self._fail("cleanlab.evaluator: 'prompt', 'response' and api_key are required.")
        try:
            from cleanlab_tlm import TLM
            tlm = TLM(api_key=key, options={"model": model})
            result = tlm.get_trustworthiness_score(prompt, response)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"cleanlab.evaluator: {type(exc).__name__}: {exc}")
        score = result.get("trustworthiness_score", 0.0) if isinstance(result, dict) else result
        return self._ok(f"Trust score: {score}.", score=score,
                        explanation=(result.get("log", {}) if isinstance(result, dict) else None))
