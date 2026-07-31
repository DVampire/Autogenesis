"""VLM Run Transcription."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class VlmrunTranscriptionTool(PluginTool):
    """VLM Run Transcription."""

    name: str = 'vlmrun_transcription'
    display_name: str = 'VLM Run Transcription'
    description: str = 'Extract structured data from audio and video using [VLM Run AI](https://app.vlm.run)'

    async def __call__(self, url: str = "", api_key: str = "", domain: str = "document.markdown", **kwargs) -> Response:
        key = self._secret(api_key, "VLMRUN_API_KEY")
        if not url or not key:
            return self._fail("vlmrun: 'url' and api_key (VLMRUN_API_KEY) are required.")
        try:
            from vlmrun.client import VLMRun
            client = VLMRun(api_key=key)
            result = client.document.generate(url=url, domain=domain)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"vlmrun: {type(exc).__name__}: {exc}")
        return self._ok("VLM Run transcription completed.", result=str(result))
