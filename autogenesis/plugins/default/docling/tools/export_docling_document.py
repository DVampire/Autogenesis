"""Export DoclingDocument."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DoclingExportDoclingDocumentTool(PluginTool):
    """Export DoclingDocument."""

    name: str = 'export_docling_document'
    display_name: str = 'Export DoclingDocument'
    description: str = 'Export DoclingDocument to markdown, html or other formats.'

    async def __call__(self, source: str = "", export_format: str = "markdown", **kwargs) -> Response:
        src = str(source or "").strip()
        if not src:
            return self._fail("docling.export: 'source' is required.")
        try:
            from docling.document_converter import DocumentConverter
            doc = DocumentConverter().convert(src).document
            out = doc.export_to_markdown() if export_format == "markdown" else doc.export_to_dict()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"docling.export: {type(exc).__name__}: {exc}")
        return self._ok(f"Exported document as {export_format}.", content=out, format=export_format)
