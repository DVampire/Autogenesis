"""Weaviate plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.weaviate import WeaviateTool


@PLUGIN.register_module(force=True)
class WeaviatePlugin(Plugin):
    """Weaviate tools."""

    tools = (WeaviateTool,)

    name: str = 'weaviate'
    display_name: str = 'Weaviate'
    description: str = 'Weaviate tools.'
    category: str = 'data'
    type: str = 'vectorstore'
