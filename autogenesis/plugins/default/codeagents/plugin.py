"""Code Agents plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.codeact_agent_smolagents import CodeagentsCodeactAgentSmolagentsTool
from .tools.open_ds_star_agent import CodeagentsOpenDsStarAgentTool


@PLUGIN.register_module(force=True)
class CodeagentsPlugin(Plugin):
    """Code Agents tools."""

    tools = (CodeagentsCodeactAgentSmolagentsTool, CodeagentsOpenDsStarAgentTool,)

    name: str = 'codeagents'
    display_name: str = 'Code Agents'
    description: str = 'Code Agents tools.'
    category: str = 'agent'
    type: str = 'tool'
