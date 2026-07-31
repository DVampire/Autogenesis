"""LM Studio Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class LmstudioembeddingsTool(EmbeddingPluginTool):
    """LM Studio Embeddings."""

    name: str = 'lmstudioembeddings'
    display_name: str = 'LM Studio Embeddings'
    description: str = 'Generate embeddings using LM Studio.'
    key_env: str = 'LMSTUDIO_API_KEY'
    default_base_url: str = 'http://localhost:1234/v1'

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_openai import OpenAIEmbeddings
        key = self._secret(cfg.get("api_key"), self.key_env, "OPENAI_API_KEY")
        if not key:
            raise ValueError(f"no API key (set api_key or {self.key_env or 'OPENAI_API_KEY'}).")
        return OpenAIEmbeddings(model=cfg.get("model_name"), api_key=key,
                               base_url=(cfg.get("base_url") or self.default_base_url or None))

    async def __call__(self, text: str = "", model_name: str = "text-embedding-nomic-embed-text-v1.5", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
