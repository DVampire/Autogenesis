"""DuckDuckGo plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.duck_duck_go_search_run import DuckduckgoDuckDuckGoSearchRunTool


@PLUGIN.register_module(force=True)
class DuckduckgoPlugin(Plugin):
    """DuckDuckGo tools."""

    tools = (DuckduckgoDuckDuckGoSearchRunTool,)

    name: str = 'duckduckgo'
    display_name: str = 'DuckDuckGo'
    description: str = 'DuckDuckGo tools.'
    category: str = 'data'
    type: str = 'tool'
