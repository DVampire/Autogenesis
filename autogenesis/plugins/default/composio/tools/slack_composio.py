"""Slack (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioSlackComposioTool(ComposioPluginTool):
    """Slack."""

    name: str = 'slack_composio'
    display_name: str = 'Slack'
    description: str = 'Execute Slack actions via Composio.'
    app_name: str = 'slack'
