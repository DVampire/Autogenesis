"""CUGA plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.agent import CugaAgentTool


@PLUGIN.register_module(force=True)
class CugaPlugin(Plugin):
    """CUGA tools."""

    tools = (CugaAgentTool,)

    name: str = 'cuga'
    display_name: str = 'CUGA'
    description: str = 'CUGA tools.'
    category: str = 'agent'
    type: str = 'tool'
