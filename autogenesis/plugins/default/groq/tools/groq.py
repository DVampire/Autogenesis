"""Groq."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class GroqTool(LLMPluginTool):
    """Groq."""

    name: str = 'groq'
    display_name: str = 'Groq'
    description: str = 'Generate text using Groq.'
    default_base_url: str = ''
    key_env: str = 'GROQ_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        from langchain_groq import ChatGroq
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or GROQ_API_KEY).")
        kw = {"model_name": cfg.get("model_name"), "api_key": key, "temperature": cfg.get("temperature", 0.1)}
        if cfg.get("base_url"):
            kw["base_url"] = cfg["base_url"]
        return ChatGroq(**kw)

    async def __call__(self, prompt: str = "", model_name: str = "llama-3.3-70b-versatile", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
