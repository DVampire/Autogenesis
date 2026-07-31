"""IBM watsonx.ai Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class IbmWatsonxEmbeddingsTool(EmbeddingPluginTool):
    """IBM watsonx.ai Embeddings."""

    name: str = 'watsonx_embeddings'
    display_name: str = 'IBM watsonx.ai Embeddings'
    description: str = 'Generate embeddings using IBM watsonx.ai models.'
    type: str = 'embedding'

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_ibm import WatsonxEmbeddings
        key = self._secret(cfg.get("api_key"), "WATSONX_APIKEY")
        url = cfg.get("base_url") or self._secret("", "WATSONX_URL")
        project = self._secret("", "WATSONX_PROJECT_ID")
        if not key or not url or not project:
            raise ValueError("watsonx needs WATSONX_APIKEY, WATSONX_URL, WATSONX_PROJECT_ID.")
        return WatsonxEmbeddings(model_id=cfg.get("model_name"), url=url, apikey=key, project_id=project)

    async def __call__(self, text: str = "", model_name: str = "ibm/slate-125m-english-rtrvr", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
