"""Slackbot (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioSlackbotComposioTool(ComposioPluginTool):
    """Slackbot."""

    name: str = 'slackbot_composio'
    display_name: str = 'Slackbot'
    description: str = 'Execute Slackbot actions via Composio.'
    app_name: str = 'slackbot'
