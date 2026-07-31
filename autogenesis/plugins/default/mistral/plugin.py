"""MistralAI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.embeddings import MistralEmbeddingsTool
from .tools.mistral import MistralTool


@PLUGIN.register_module(force=True)
class MistralPlugin(Plugin):
    """MistralAI tools."""

    tools = (MistralTool, MistralEmbeddingsTool,)

    name: str = 'mistral'
    display_name: str = 'MistralAI'
    description: str = 'MistralAI tools.'
    category: str = 'data'
    type: str = 'model'
