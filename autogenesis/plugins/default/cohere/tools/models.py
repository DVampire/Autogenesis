"""Cohere Language Models."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class CohereModelsTool(LLMPluginTool):
    """Cohere Language Models."""

    name: str = 'cohere_models'
    display_name: str = 'Cohere Language Models'
    description: str = 'Generate text using Cohere LLMs.'
    type: str = 'model'
    default_base_url: str = ''
    key_env: str = 'COHERE_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        from langchain_cohere import ChatCohere
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or COHERE_API_KEY).")
        return ChatCohere(model=cfg.get("model_name"), cohere_api_key=key,
                          temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "command-r-plus", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
