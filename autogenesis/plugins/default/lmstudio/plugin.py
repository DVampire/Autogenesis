"""LM Studio plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.lmstudioembeddings import LmstudioembeddingsTool
from .tools.lmstudiomodel import LmstudiomodelTool


@PLUGIN.register_module(force=True)
class LmstudioPlugin(Plugin):
    """LM Studio tools."""

    tools = (LmstudioembeddingsTool, LmstudiomodelTool,)

    name: str = 'lmstudio'
    display_name: str = 'LM Studio'
    description: str = 'LM Studio tools.'
    category: str = 'data'
    type: str = 'embedding'
