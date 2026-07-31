"""Vectara plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.rag import VectaraRagTool
from .tools.vectara import VectaraTool


@PLUGIN.register_module(force=True)
class VectaraPlugin(Plugin):
    """Vectara tools."""

    tools = (VectaraTool, VectaraRagTool,)

    name: str = 'vectara'
    display_name: str = 'Vectara'
    description: str = 'Vectara tools.'
    category: str = 'data'
    type: str = 'vectorstore'
