"""Spider plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.spider import SpiderTool


@PLUGIN.register_module(force=True)
class SpiderPlugin(Plugin):
    """Spider tools."""

    tools = (SpiderTool,)

    name: str = 'spider'
    display_name: str = 'Spider'
    description: str = 'Spider tools.'
    category: str = 'data'
    type: str = 'tool'
