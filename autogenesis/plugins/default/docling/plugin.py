"""Docling plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chunk_docling_document import DoclingChunkDoclingDocumentTool
from .tools.export_docling_document import DoclingExportDoclingDocumentTool
from .tools.inline import DoclingInlineTool
from .tools.remote import DoclingRemoteTool


@PLUGIN.register_module(force=True)
class DoclingPlugin(Plugin):
    """Docling tools."""

    tools = (
        DoclingChunkDoclingDocumentTool,
        DoclingInlineTool,
        DoclingRemoteTool,
        DoclingExportDoclingDocumentTool,
    )

    name: str = 'docling'
    display_name: str = 'Docling'
    description: str = 'Docling tools.'
    category: str = 'files'
    type: str = 'tool'
