"""Ollama."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class OllamaTool(LLMPluginTool):
    """Ollama."""

    name: str = 'ollama'
    display_name: str = 'Ollama'
    description: str = 'Generate text using Ollama Local LLMs.'
    default_base_url: str = 'http://localhost:11434'
    key_env: str = ''

    def _model(self, **cfg: Any) -> Any:
        from langchain_ollama import ChatOllama
        return ChatOllama(model=cfg.get("model_name"),
                          base_url=cfg.get("base_url") or self.default_base_url,
                          temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "llama3.1", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
