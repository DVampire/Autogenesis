"""TwelveLabs Video Embeddings."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class TwelvelabsVideoEmbeddingsTool(PluginTool):
    """TwelveLabs Video Embeddings."""

    name: str = 'video_embeddings'
    display_name: str = 'TwelveLabs Video Embeddings'
    description: str = 'Generate embeddings from videos using TwelveLabs video embedding models.'
    category: str = 'knowledge'

    async def __call__(self, video_url: str = "", api_key: str = "", model_name: str = "Marengo-retrieval-2.7", **kwargs) -> Response:
        key = self._secret(api_key, "TWELVELABS_API_KEY")
        if not video_url or not key:
            return self._fail("twelvelabs.video_embeddings: 'video_url' and api_key are required.")
        try:
            from twelvelabs import TwelveLabs
            client = TwelveLabs(api_key=key)
            task = client.embed.task.create(model_name=model_name, video_url=video_url)
            task.wait_for_done()
            result = client.embed.task.retrieve(task.id)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"twelvelabs.video_embeddings: {type(exc).__name__}: {exc}")
        return self._ok("Video embedded.", result=str(result))
