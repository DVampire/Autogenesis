"""Outlook (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioOutlookComposioTool(ComposioPluginTool):
    """Outlook."""

    name: str = 'outlook_composio'
    display_name: str = 'Outlook'
    description: str = 'Execute Outlook actions via Composio.'
    app_name: str = 'outlook'
