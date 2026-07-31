"""Miro (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioMiroComposioTool(ComposioPluginTool):
    """Miro."""

    name: str = 'miro_composio'
    display_name: str = 'Miro'
    description: str = 'Execute Miro actions via Composio.'
    app_name: str = 'miro'
