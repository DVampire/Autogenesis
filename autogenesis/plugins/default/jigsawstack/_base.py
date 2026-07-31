"""Shared base for the JigsawStack provider tools (ported from Langflow).

Every JigsawStack component calls the ``jigsawstack`` SDK:
``JigsawStack(api_key).<path>(params)``. The base resolves the client + the
dotted method path and returns the canonical Response. Key resolves from the
arg, the ``jigsawstack_plugin`` config block, or ``JIGSAWSTACK_API_KEY``.
"""

from __future__ import annotations

from typing import Any, Dict

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class JigsawstackToolBase(PluginTool):
    """Base for JigsawStack tools — SDK client + dotted-path dispatch."""

    category: str = "data"

    async def _run(self, method_path: str, params: Dict[str, Any], api_key: str = "") -> Response:
        key = self._secret(api_key, "JIGSAWSTACK_API_KEY")
        if not key:
            return self._fail(f"{self.name}: no API key (set api_key or JIGSAWSTACK_API_KEY).")
        try:
            from jigsawstack import JigsawStack

            target: Any = JigsawStack(api_key=key)
            for part in method_path.split("."):
                target = getattr(target, part)
            result = target(params)
        except Exception as exc:  # noqa: BLE001 — missing SDK / API error
            return self._fail(f"{self.name}: {type(exc).__name__}: {exc}")
        return self._ok(f"{self.plugin_label}: {method_path} completed.", result=result)
