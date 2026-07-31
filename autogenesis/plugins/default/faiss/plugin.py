"""FAISS plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.faiss import FaissTool


@PLUGIN.register_module(force=True)
class FaissPlugin(Plugin):
    """FAISS tools."""

    tools = (FaissTool,)

    name: str = 'faiss'
    display_name: str = 'FAISS'
    description: str = 'FAISS tools.'
    category: str = 'data'
    type: str = 'vectorstore'
