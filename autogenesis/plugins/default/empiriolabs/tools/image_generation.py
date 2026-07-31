"""EmpirioLabs AI Image Generation."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class EmpiriolabsImageGenerationTool(PluginTool):
    """EmpirioLabs AI Image Generation."""

    name: str = 'empiriolabs_image_generation'
    display_name: str = 'EmpirioLabs AI Image Generation'
    description: str = 'Generate an image from a text prompt using EmpirioLabs AI image models such as Seedream, \\\\\\\\\\\\n        Qwen-Image, FLUX, Nova Canvas, and HunyuanImage.'
    category: str = 'data'

    async def __call__(self, prompt: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        key = self._secret(api_key, "EMPIRIOLABS_API_KEY")
        if not prompt or not key:
            return self._fail("empiriolabs.image: 'prompt' and api_key are required.")
        try:
            resp = httpx.post("https://api.empiriolabs.ai/v1/images/generations",
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"prompt": prompt}, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"empiriolabs.image: {type(exc).__name__}: {exc}")
        return self._ok("Image generated.", result=data)
