"""TwelveLabs Pegasus Index Video."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class TwelvelabsPegasusIndexTool(PluginTool):
    """TwelveLabs Pegasus Index Video."""

    name: str = 'pegasus_index'
    display_name: str = 'TwelveLabs Pegasus Index Video'
    description: str = 'Index videos using TwelveLabs and add the video_id to metadata.'

    async def __call__(self, index_name: str = "", api_key: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "TWELVELABS_API_KEY")
        if not index_name or not key:
            return self._fail("twelvelabs.pegasus_index: 'index_name' and api_key are required.")
        try:
            from twelvelabs import TwelveLabs
            idx = TwelveLabs(api_key=key).index.create(name=index_name,
                    models=[{"name": "pegasus1.2", "options": ["visual", "audio"]}])
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"twelvelabs.pegasus_index: {type(exc).__name__}: {exc}")
        return self._ok(f"Created index '{index_name}'.", index_id=getattr(idx, "id", None))
