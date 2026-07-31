"""File Upload."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackFileUploadTool(JigsawstackToolBase):
    """File Upload."""

    name: str = 'file_upload'
    display_name: str = 'File Upload'
    description: str = 'Store any file seamlessly on JigsawStack File Storage and use it in your AI applications. \\\\\\\\\\\\n        Supports various file types including images, documents, and more.'

    async def __call__(self, file: str = "", key: str = "", overwrite: bool = False, api_key: str = "", **kwargs) -> Response:
        params = {"file": file, "key": key, "overwrite": overwrite}
        return await self._run("store.upload", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
