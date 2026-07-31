"""EmpirioLabs AI."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class EmpiriolabsTool(PluginTool):
    """EmpirioLabs AI."""

    name: str = 'empiriolabs'
    display_name: str = 'EmpirioLabs AI'
    description: str = 'Generates text using EmpirioLabs AI LLMs (OpenAI compatible).'

    async def __call__(self, prompt: str = "", model: str = "", api_key: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "EMPIRIOLABS_API_KEY")
        if not prompt or not key:
            return self._fail("empiriolabs: 'prompt' and api_key are required.")
        try:
            from langchain_openai import ChatOpenAI
            model_ = ChatOpenAI(model=model or "gpt-4o-mini", api_key=key,
                               base_url="https://api.empiriolabs.ai/v1")
            out = model_.invoke(prompt)
            text = out.content if hasattr(out, "content") else str(out)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"empiriolabs: {type(exc).__name__}: {exc}")
        return self._ok(str(text), text=str(text))
