"""Chunk DoclingDocument."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DoclingChunkDoclingDocumentTool(PluginTool):
    """Chunk DoclingDocument."""

    name: str = 'chunk_docling_document'
    display_name: str = 'Chunk DoclingDocument'
    description: str = 'Use DoclingDocument chunkers to split the document into chunks.'

    async def __call__(self, source: str = "", max_tokens: int = 512, **kwargs) -> Response:
        src = str(source or "").strip()
        if not src:
            return self._fail("docling.chunk: 'source' is required.")
        try:
            from docling.document_converter import DocumentConverter
            from docling.chunking import HybridChunker
            doc = DocumentConverter().convert(src).document
            chunks = list(HybridChunker(max_tokens=int(max_tokens)).chunk(doc))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"docling.chunk: {type(exc).__name__}: {exc}")
        records = [{"content": getattr(c, "text", str(c))} for c in chunks]
        return self._ok(f"Chunked into {len(records)} pieces.", records=records, count=len(records))
