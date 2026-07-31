"""Docling."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DoclingInlineTool(PluginTool):
    """Docling."""

    name: str = 'docling_inline'
    display_name: str = 'Docling'
    description: str = 'Uses Docling to process input documents running the Docling models locally.'

    async def __call__(self, source: str = "", **kwargs) -> Response:
        src = str(source or "").strip()
        if not src:
            return self._fail("docling.inline: 'source' (file path or URL) is required.")
        try:
            from docling.document_converter import DocumentConverter
            result = DocumentConverter().convert(src)
            doc = result.document
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"docling.inline: {type(exc).__name__}: {exc}")
        return self._ok("Converted document.", markdown=doc.export_to_markdown())
