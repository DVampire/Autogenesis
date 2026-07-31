"""AI/ML API plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.aiml import AimlTool
from .tools.embeddings import AimlEmbeddingsTool


@PLUGIN.register_module(force=True)
class AimlPlugin(Plugin):
    """AI/ML API tools."""

    tools = (AimlTool, AimlEmbeddingsTool,)

    name: str = 'aiml'
    display_name: str = 'AI/ML API'
    description: str = 'AI/ML API tools.'
    category: str = 'data'
    type: str = 'model'
