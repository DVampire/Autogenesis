"""Perplexity."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class PerplexityTool(LLMPluginTool):
    """Perplexity."""

    name: str = 'perplexity'
    display_name: str = 'Perplexity'
    description: str = 'Generate text using Perplexity LLMs.'
    default_base_url: str = 'https://api.perplexity.ai'
    key_env: str = 'PERPLEXITY_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        return self._openai_compatible(cfg.get("model_name"), cfg.get("api_key", ""),
                                       cfg.get("base_url", ""), cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "sonar", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
