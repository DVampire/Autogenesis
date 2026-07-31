"""OpenAI."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class OpenaiChatModelTool(LLMPluginTool):
    """OpenAI."""

    name: str = 'openai_chat_model'
    display_name: str = 'OpenAI'
    description: str = 'Generates text using OpenAI LLMs.'
    type: str = 'model'
    default_base_url: str = ''
    key_env: str = 'OPENAI_API_KEY'

    def _model(self, **cfg: Any) -> Any:
        return self._openai_compatible(cfg.get("model_name"), cfg.get("api_key", ""),
                                       cfg.get("base_url", ""), cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "gpt-4o-mini", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
