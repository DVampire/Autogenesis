"""Cleanlab Remediator."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class CleanlabRemediatorTool(PluginTool):
    """Cleanlab Remediator."""

    name: str = 'cleanlab_remediator'
    display_name: str = 'Cleanlab Remediator'
    description: str = ''

    async def __call__(self, response: str = "", score: float = 0.0, threshold: float = 0.7, fallback: str = "I am not sure.", **kwargs) -> Response:
        if not response:
            return self._fail("cleanlab.remediator: 'response' is required.")
        remediated = response if float(score) >= float(threshold) else fallback
        return self._ok("Remediation applied." if remediated == fallback else "Response passed threshold.",
                        response=remediated, remediated=remediated == fallback, score=score)
