"""MistralAI."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class MistralTool(LLMPluginTool):
    """MistralAI."""

    name: str = 'mistral'
    display_name: str = 'MistralAI'
    description: str = 'Generates text using MistralAI LLMs.'
    default_base_url: str = ''
    key_env: str = 'MISTRAL_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        from langchain_mistralai import ChatMistralAI
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or MISTRAL_API_KEY).")
        return ChatMistralAI(model_name=cfg.get("model_name"), mistral_api_key=key,
                             temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "mistral-large-latest", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
