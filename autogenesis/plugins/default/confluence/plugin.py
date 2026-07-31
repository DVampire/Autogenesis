"""Confluence plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.confluence import ConfluenceTool


@PLUGIN.register_module(force=True)
class ConfluencePlugin(Plugin):
    """Confluence tools."""

    tools = (ConfluenceTool,)

    name: str = 'confluence'
    display_name: str = 'Confluence'
    description: str = 'Confluence tools.'
    category: str = 'data'
    type: str = 'tool'
