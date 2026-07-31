"""Anthropic plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.anthropic import AnthropicTool


@PLUGIN.register_module(force=True)
class AnthropicPlugin(Plugin):
    """Anthropic tools."""

    tools = (AnthropicTool,)

    name: str = 'anthropic'
    display_name: str = 'Anthropic'
    description: str = 'Anthropic tools.'
    category: str = 'data'
    type: str = 'model'
