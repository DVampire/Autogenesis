"""NVIDIA Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class NvidiaEmbeddingTool(EmbeddingPluginTool):
    """NVIDIA Embeddings."""

    name: str = 'nvidia_embedding'
    display_name: str = 'NVIDIA Embeddings'
    description: str = 'Generate embeddings using NVIDIA models.'
    type: str = 'embedding'
    key_env: str = 'NVIDIA_API_KEY'
    default_base_url: str = ''

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or NVIDIA_API_KEY).")
        return NVIDIAEmbeddings(model=cfg.get("model_name"), api_key=key)

    async def __call__(self, text: str = "", model_name: str = "NV-Embed-QA", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
