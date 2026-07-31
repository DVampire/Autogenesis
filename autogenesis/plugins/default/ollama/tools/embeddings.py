"""Ollama Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class OllamaEmbeddingsTool(EmbeddingPluginTool):
    """Ollama Embeddings."""

    name: str = 'ollama_embeddings'
    display_name: str = 'Ollama Embeddings'
    description: str = 'Generate embeddings using Ollama models.'
    type: str = 'embedding'
    key_env: str = ''
    default_base_url: str = 'http://localhost:11434'

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(model=cfg.get("model_name"),
                               base_url=cfg.get("base_url") or self.default_base_url)

    async def __call__(self, text: str = "", model_name: str = "nomic-embed-text", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
