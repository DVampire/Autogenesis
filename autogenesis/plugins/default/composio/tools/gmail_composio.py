"""Gmail (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGmailComposioTool(ComposioPluginTool):
    """Gmail."""

    name: str = 'gmail_composio'
    display_name: str = 'Gmail'
    description: str = 'Execute Gmail actions via Composio.'
    app_name: str = 'gmail'
