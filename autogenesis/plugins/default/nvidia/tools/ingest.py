"""NVIDIA Retriever Extraction."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class NvidiaIngestTool(PluginTool):
    """NVIDIA Retriever Extraction."""

    name: str = 'nvidia_ingest'
    display_name: str = 'NVIDIA Retriever Extraction'
    description: str = 'Multi-modal data extraction from documents using NVIDIA'
    category: str = 'data'

    async def __call__(self, file_path: str = "", base_url: str = "", api_key: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "NVIDIA_API_KEY")
        if not file_path:
            return self._fail("nvidia.ingest: 'file_path' is required.")
        try:
            from nv_ingest_client.client import Ingestor
            ingestor = Ingestor(message_client_hostname=base_url or "localhost")
            result = ingestor.files(file_path).extract().ingest()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"nvidia.ingest: {type(exc).__name__}: {exc}")
        return self._ok("NVIDIA ingest completed.", result=str(result))
