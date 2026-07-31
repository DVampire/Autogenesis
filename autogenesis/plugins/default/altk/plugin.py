"""ALTK plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.agent import AltkAgentTool


@PLUGIN.register_module(force=True)
class AltkPlugin(Plugin):
    """ALTK tools."""

    tools = (AltkAgentTool,)

    name: str = 'altk'
    display_name: str = 'ALTK'
    description: str = 'ALTK tools.'
    category: str = 'agent'
    type: str = 'tool'
