"""Qdrant plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.qdrant import QdrantTool


@PLUGIN.register_module(force=True)
class QdrantPlugin(Plugin):
    """Qdrant tools."""

    tools = (QdrantTool,)

    name: str = 'qdrant'
    display_name: str = 'Qdrant'
    description: str = 'Qdrant tools.'
    category: str = 'data'
    type: str = 'vectorstore'
