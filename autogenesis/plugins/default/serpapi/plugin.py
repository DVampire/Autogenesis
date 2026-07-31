"""SerpAPI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.serp import SerpapiSerpTool


@PLUGIN.register_module(force=True)
class SerpapiPlugin(Plugin):
    """SerpAPI tools."""

    tools = (SerpapiSerpTool,)

    name: str = 'serpapi'
    display_name: str = 'SerpAPI'
    description: str = 'SerpAPI tools.'
    category: str = 'data'
    type: str = 'tool'
