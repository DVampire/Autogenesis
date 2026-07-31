"""TwelveLabs Pegasus."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class TwelvelabsPegasusTool(PluginTool):
    """TwelveLabs Pegasus."""

    name: str = 'twelvelabs_pegasus'
    display_name: str = 'TwelveLabs Pegasus'
    description: str = 'Chat with videos using TwelveLabs Pegasus API.'

    async def __call__(self, video_id: str = "", index_id: str = "", prompt: str = "", api_key: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "TWELVELABS_API_KEY", "TWELVE_LABS_API_KEY")
        if not video_id or not prompt or not key:
            return self._fail("twelvelabs.pegasus: 'video_id', 'prompt' and api_key are required.")
        try:
            from twelvelabs import TwelveLabs
            client = TwelveLabs(api_key=key)
            result = client.generate.text(video_id=video_id, prompt=prompt)
            text = getattr(result, "data", None) or getattr(result, "text", None) or str(result)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"twelvelabs.pegasus: {type(exc).__name__}: {exc}")
        return self._ok(str(text), video_id=video_id, text=str(text))
