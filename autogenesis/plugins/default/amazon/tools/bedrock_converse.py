"""Amazon Bedrock Converse."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class AmazonBedrockConverseTool(LLMPluginTool):
    """Amazon Bedrock Converse."""

    name: str = 'amazon_bedrock_converse'
    display_name: str = 'Amazon Bedrock Converse'
    description: str = 'Amazon Bedrock Converse'

    def _model(self, **cfg: Any) -> Any:
        from langchain_aws import ChatBedrockConverse
        return ChatBedrockConverse(model=cfg.get("model_name"),
                                  region_name=self._secret("", "AWS_REGION") or "us-east-1",
                                  temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "anthropic.claude-3-5-sonnet-20240620-v1:0", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
