"""NVIDIA."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class NvidiaTool(LLMPluginTool):
    """NVIDIA."""

    name: str = 'nvidia'
    display_name: str = 'NVIDIA'
    description: str = 'Generates text using NVIDIA LLMs.'
    type: str = 'model'
    default_base_url: str = ''
    key_env: str = 'NVIDIA_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        key = self._secret(cfg.get("api_key"), self.key_env)
        if not key:
            raise ValueError("no API key (set api_key or NVIDIA_API_KEY).")
        kw = {"model": cfg.get("model_name"), "api_key": key, "temperature": cfg.get("temperature", 0.1)}
        if cfg.get("base_url"):
            kw["base_url"] = cfg["base_url"]
        return ChatNVIDIA(**kw)

    async def __call__(self, prompt: str = "", model_name: str = "meta/llama-3.1-8b-instruct", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
