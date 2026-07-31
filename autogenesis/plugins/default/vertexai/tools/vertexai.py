"""Vertex AI."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class VertexaiTool(LLMPluginTool):
    """Vertex AI."""

    name: str = 'vertexai'
    display_name: str = 'Vertex AI'
    description: str = 'Generate text using Vertex AI LLMs.'

    def _model(self, **cfg: Any) -> Any:
        from langchain_google_vertexai import ChatVertexAI
        return ChatVertexAI(model_name=cfg.get("model_name"), temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "gemini-1.5-flash", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
