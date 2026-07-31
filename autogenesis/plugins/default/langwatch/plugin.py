"""LangWatch plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.langwatch import LangwatchTool


@PLUGIN.register_module(force=True)
class LangwatchPlugin(Plugin):
    """LangWatch tools."""

    tools = (LangwatchTool,)

    name: str = 'langwatch'
    display_name: str = 'LangWatch'
    description: str = 'LangWatch tools.'
    category: str = 'evaluation'
    type: str = 'tool'
