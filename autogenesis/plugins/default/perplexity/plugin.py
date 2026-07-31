"""Perplexity plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.perplexity import PerplexityTool


@PLUGIN.register_module(force=True)
class PerplexityPlugin(Plugin):
    """Perplexity tools."""

    tools = (PerplexityTool,)

    name: str = 'perplexity'
    display_name: str = 'Perplexity'
    description: str = 'Perplexity tools.'
    category: str = 'data'
    type: str = 'model'
