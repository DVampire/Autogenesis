"""Image Generation."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackImageGenerationTool(JigsawstackToolBase):
    """Image Generation."""

    name: str = 'image_generation'
    display_name: str = 'Image Generation'
    description: str = 'Generate an image based on the given text by employing AI models like Flux, \\\\\\\\\\\\n        Stable Diffusion, and other top models.'

    async def __call__(self, prompt: str = "", aspect_ratio: str = "1:1", api_key: str = "", **kwargs) -> Response:
        params = {"prompt": prompt, "aspect_ratio": aspect_ratio}
        return await self._run("image_generation", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
