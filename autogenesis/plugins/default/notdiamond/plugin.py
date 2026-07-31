"""Not Diamond plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.notdiamond import NotdiamondTool


@PLUGIN.register_module(force=True)
class NotdiamondPlugin(Plugin):
    """Not Diamond tools."""

    tools = (NotdiamondTool,)

    name: str = 'notdiamond'
    display_name: str = 'Not Diamond'
    description: str = 'Not Diamond tools.'
    category: str = 'agent'
    type: str = 'tool'
