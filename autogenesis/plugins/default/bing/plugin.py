"""Bing plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.search_api import BingSearchApiTool


@PLUGIN.register_module(force=True)
class BingPlugin(Plugin):
    """Bing tools."""

    tools = (BingSearchApiTool,)

    name: str = 'bing'
    display_name: str = 'Bing'
    description: str = 'Bing tools.'
    category: str = 'data'
    type: str = 'tool'
