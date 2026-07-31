"""Cohere Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class CohereEmbeddingsTool(EmbeddingPluginTool):
    """Cohere Embeddings."""

    name: str = 'cohere_embeddings'
    display_name: str = 'Cohere Embeddings'
    description: str = 'Generate embeddings using Cohere models.'
    key_env: str = 'COHERE_API_KEY'
    default_base_url: str = ''

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_cohere import CohereEmbeddings
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or COHERE_API_KEY).")
        return CohereEmbeddings(model=cfg.get("model_name"), cohere_api_key=key)

    async def __call__(self, text: str = "", model_name: str = "embed-english-v3.0", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
