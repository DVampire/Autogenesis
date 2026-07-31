"""AgentQL plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.api import AgentqlApiTool


@PLUGIN.register_module(force=True)
class AgentqlPlugin(Plugin):
    """AgentQL tools."""

    tools = (AgentqlApiTool,)

    name: str = 'agentql'
    display_name: str = 'AgentQL'
    description: str = 'AgentQL tools.'
    category: str = 'data'
    type: str = 'tool'
