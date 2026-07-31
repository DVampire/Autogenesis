"""AgentQL (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioAgentqlComposioTool(ComposioPluginTool):
    """AgentQL."""

    name: str = 'agentql_composio'
    display_name: str = 'AgentQL'
    description: str = 'Execute AgentQL actions via Composio.'
    app_name: str = 'agentql'
