"""Pinecone plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.pinecone import PineconeTool


@PLUGIN.register_module(force=True)
class PineconePlugin(Plugin):
    """Pinecone tools."""

    tools = (PineconeTool,)

    name: str = 'pinecone'
    display_name: str = 'Pinecone'
    description: str = 'Pinecone tools.'
    category: str = 'data'
    type: str = 'vectorstore'
