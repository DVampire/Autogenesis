"""Hugging Face."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class HuggingfaceTool(LLMPluginTool):
    """Hugging Face."""

    name: str = 'huggingface'
    display_name: str = 'Hugging Face'
    description: str = 'Generate text using Hugging Face Inference APIs.'

    def _model(self, **cfg: Any) -> Any:
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
        key = self._secret(cfg.get("api_key"), "HUGGINGFACEHUB_API_TOKEN", "HF_TOKEN")
        if not key:
            raise ValueError("no API key (set api_key or HUGGINGFACEHUB_API_TOKEN).")
        endpoint = HuggingFaceEndpoint(repo_id=cfg.get("model_name"), huggingfacehub_api_token=key,
                                      temperature=cfg.get("temperature", 0.1) or 0.1)
        return ChatHuggingFace(llm=endpoint)

    async def __call__(self, prompt: str = "", model_name: str = "HuggingFaceH4/zephyr-7b-beta", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
