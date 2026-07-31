"""Agiled (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioAgiledComposioTool(ComposioPluginTool):
    """Agiled."""

    name: str = 'agiled_composio'
    display_name: str = 'Agiled'
    description: str = 'Execute Agiled actions via Composio.'
    app_name: str = 'agiled'
