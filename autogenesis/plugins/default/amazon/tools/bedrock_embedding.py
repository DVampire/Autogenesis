"""Amazon Bedrock Embeddings."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import EmbeddingPluginTool


class AmazonBedrockEmbeddingTool(EmbeddingPluginTool):
    """Amazon Bedrock Embeddings."""

    name: str = 'amazon_bedrock_embedding'
    display_name: str = 'Amazon Bedrock Embeddings'
    description: str = 'Generate embeddings using Amazon Bedrock models.'
    type: str = 'embedding'

    def _embeddings(self, **cfg: Any) -> Any:
        from langchain_aws import BedrockEmbeddings
        return BedrockEmbeddings(model_id=cfg.get("model_name"),
                                region_name=self._secret("", "AWS_REGION") or "us-east-1")

    async def __call__(self, text: str = "", model_name: str = "amazon.titan-embed-text-v1", api_key: str = "",
                       base_url: str = "", **kwargs) -> Response:
        return await self._embed(text=text, model_name=model_name, api_key=api_key, base_url=base_url)
