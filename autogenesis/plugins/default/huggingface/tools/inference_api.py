"""Hugging Face Embeddings Inference."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class HuggingfaceInferenceApiTool(EmbeddingPluginTool):
    """Hugging Face Embeddings Inference."""

    name: str = 'huggingface_inference_api'
    display_name: str = 'Hugging Face Embeddings Inference'
    description: str = 'Generate embeddings using Hugging Face Text Embeddings Inference (TEI)'
    type: str = 'embedding'
    key_env: str = 'HUGGINGFACEHUB_API_TOKEN'
    default_base_url: str = ''

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
        key = self._secret(cfg.get("api_key"), self.key_env, "HF_TOKEN")
        if not key:
            raise ValueError("no API key (set api_key or HUGGINGFACEHUB_API_TOKEN).")
        return HuggingFaceInferenceAPIEmbeddings(api_key=key, model_name=cfg.get("model_name"))

    async def __call__(self, text: str = "", model_name: str = "sentence-transformers/all-MiniLM-L6-v2", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
