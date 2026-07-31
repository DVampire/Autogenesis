"""Digicert (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioDigicertComposioTool(ComposioPluginTool):
    """Digicert."""

    name: str = 'digicert_composio'
    display_name: str = 'Digicert'
    description: str = 'Execute Digicert actions via Composio.'
    app_name: str = 'digicert'
