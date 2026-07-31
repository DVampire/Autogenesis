"""Docling Serve."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DoclingRemoteTool(PluginTool):
    """Docling Serve."""

    name: str = 'docling_remote'
    display_name: str = 'Docling Serve'
    description: str = 'Uses Docling to process input documents connecting to your instance of Docling Serve.'

    async def __call__(self, source: str = "", **kwargs) -> Response:
        src = str(source or "").strip()
        if not src:
            return self._fail("docling.remote: 'source' (file path or URL) is required.")
        try:
            from docling.document_converter import DocumentConverter
            result = DocumentConverter().convert(src)
            doc = result.document
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"docling.remote: {type(exc).__name__}: {exc}")
        return self._ok("Converted document (remote).", markdown=doc.export_to_markdown())
