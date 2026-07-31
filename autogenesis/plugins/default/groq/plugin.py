"""Groq plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.groq import GroqTool


@PLUGIN.register_module(force=True)
class GroqPlugin(Plugin):
    """Groq tools."""

    tools = (GroqTool,)

    name: str = 'groq'
    display_name: str = 'Groq'
    description: str = 'Groq tools.'
    category: str = 'data'
    type: str = 'model'
