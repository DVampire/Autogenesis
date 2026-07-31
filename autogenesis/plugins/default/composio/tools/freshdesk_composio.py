"""Freshdesk (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFreshdeskComposioTool(ComposioPluginTool):
    """Freshdesk."""

    name: str = 'freshdesk_composio'
    display_name: str = 'Freshdesk'
    description: str = 'Execute Freshdesk actions via Composio.'
    app_name: str = 'freshdesk'
