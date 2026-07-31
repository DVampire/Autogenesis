"""Anthropic."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class AnthropicTool(LLMPluginTool):
    """Anthropic."""

    name: str = 'anthropic'
    display_name: str = 'Anthropic'
    description: str = 'Generate text using Anthropic'
    default_base_url: str = ''
    key_env: str = 'ANTHROPIC_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        from langchain_anthropic import ChatAnthropic
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or ANTHROPIC_API_KEY).")
        kw = {"model": cfg.get("model_name"), "anthropic_api_key": key, "temperature": cfg.get("temperature", 0.1)}
        if cfg.get("base_url"):
            kw["anthropic_api_url"] = cfg["base_url"]
        return ChatAnthropic(**kw)

    async def __call__(self, prompt: str = "", model_name: str = "claude-3-5-sonnet-latest", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
