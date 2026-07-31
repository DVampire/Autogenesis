"""Google Generative AI."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class GoogleGenerativeAiTool(LLMPluginTool):
    """Google Generative AI."""

    name: str = 'google_generative_ai'
    display_name: str = 'Google Generative AI'
    description: str = 'Generate text using Google Generative AI.'
    type: str = 'model'

    def _model(self, **cfg: Any) -> Any:
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = self._secret(cfg.get("api_key"), "GOOGLE_API_KEY", "GEMINI_API_KEY")
        if not key:
            raise ValueError("no API key (set api_key or GOOGLE_API_KEY).")
        return ChatGoogleGenerativeAI(model=cfg.get("model_name"), google_api_key=key,
                                     temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "gemini-1.5-flash", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
