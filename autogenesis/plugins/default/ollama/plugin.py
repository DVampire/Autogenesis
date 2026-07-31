"""Ollama plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.embeddings import OllamaEmbeddingsTool
from .tools.ollama import OllamaTool


@PLUGIN.register_module(force=True)
class OllamaPlugin(Plugin):
    """Ollama tools."""

    tools = (OllamaTool, OllamaEmbeddingsTool,)

    name: str = 'ollama'
    display_name: str = 'Ollama'
    description: str = 'Ollama tools.'
    category: str = 'data'
    type: str = 'model'
