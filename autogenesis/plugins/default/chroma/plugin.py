"""Chroma plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chroma import ChromaTool
from .tools.local_db import ChromaLocalDbTool


@PLUGIN.register_module(force=True)
class ChromaPlugin(Plugin):
    """Chroma tools."""

    tools = (ChromaTool, ChromaLocalDbTool,)

    name: str = 'chroma'
    display_name: str = 'Chroma'
    description: str = 'Chroma tools.'
    category: str = 'data'
    type: str = 'vectorstore'
