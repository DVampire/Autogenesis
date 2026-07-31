"""Zep plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.zep import ZepTool


@PLUGIN.register_module(force=True)
class ZepPlugin(Plugin):
    """Zep tools."""

    tools = (ZepTool,)

    name: str = 'zep'
    display_name: str = 'Zep'
    description: str = 'Zep tools.'
    category: str = 'agent'
    type: str = 'memory'
