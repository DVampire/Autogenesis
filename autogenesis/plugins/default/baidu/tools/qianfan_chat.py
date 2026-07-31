"""Qianfan."""

from typing import Any

from autogenesis.response.types import Response
from autogenesis.plugins.types import LLMPluginTool


class BaiduQianfanChatTool(LLMPluginTool):
    """Qianfan."""

    name: str = 'baidu_qianfan_chat'
    display_name: str = 'Qianfan'
    description: str = 'Generate text using Baidu Qianfan LLMs.'
    default_base_url: str = ''
    key_env: str = 'QIANFAN_AK'

    def _model(self, **cfg: Any) -> Any:
        from langchain_community.chat_models import QianfanChatEndpoint
        ak = self._secret(cfg.get("api_key"), "QIANFAN_AK")
        sk = self._secret("", "QIANFAN_SK")
        if not ak or not sk:
            raise ValueError("Qianfan needs QIANFAN_AK and QIANFAN_SK.")
        return QianfanChatEndpoint(model=cfg.get("model_name"), qianfan_ak=ak, qianfan_sk=sk,
                                   temperature=cfg.get("temperature", 0.1))

    async def __call__(self, prompt: str = "", model_name: str = "ERNIE-4.0-8K", api_key: str = "",
                       base_url: str = "", temperature: float = 0.1, **kwargs) -> Response:
        return await self._generate(prompt=prompt, model_name=model_name, api_key=api_key,
                                    base_url=base_url, temperature=temperature)
