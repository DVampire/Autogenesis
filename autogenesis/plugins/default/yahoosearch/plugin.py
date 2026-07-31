"""Yahoo Search plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.yahoo import YahoosearchYahooTool


@PLUGIN.register_module(force=True)
class YahoosearchPlugin(Plugin):
    """Yahoo Search tools."""

    tools = (YahoosearchYahooTool,)

    name: str = 'yahoosearch'
    display_name: str = 'Yahoo Search'
    description: str = 'Yahoo Search tools.'
    category: str = 'data'
    type: str = 'tool'
