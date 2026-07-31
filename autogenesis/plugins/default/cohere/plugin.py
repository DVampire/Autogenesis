"""Cohere plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.embeddings import CohereEmbeddingsTool
from .tools.models import CohereModelsTool
from .tools.rerank import CohereRerankTool


@PLUGIN.register_module(force=True)
class CoherePlugin(Plugin):
    """Cohere tools."""

    tools = (CohereEmbeddingsTool, CohereModelsTool, CohereRerankTool,)

    name: str = 'cohere'
    display_name: str = 'Cohere'
    description: str = 'Cohere tools.'
    category: str = 'data'
    type: str = 'embedding'
