"""SearchApi plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.search import SearchapiSearchTool


@PLUGIN.register_module(force=True)
class SearchapiPlugin(Plugin):
    """SearchApi tools."""

    tools = (SearchapiSearchTool,)

    name: str = 'searchapi'
    display_name: str = 'SearchApi'
    description: str = 'SearchApi tools.'
    category: str = 'data'
    type: str = 'tool'
