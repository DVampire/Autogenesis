"""Vertex AI Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class VertexaiEmbeddingsTool(EmbeddingPluginTool):
    """Vertex AI Embeddings."""

    name: str = 'vertexai_embeddings'
    display_name: str = 'Vertex AI Embeddings'
    description: str = 'Generate embeddings using Google Cloud Vertex AI models.'
    type: str = 'embedding'

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_google_vertexai import VertexAIEmbeddings
        return VertexAIEmbeddings(model_name=cfg.get("model_name"))

    async def __call__(self, text: str = "", model_name: str = "text-embedding-004", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
