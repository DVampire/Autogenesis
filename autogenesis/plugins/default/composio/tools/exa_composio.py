"""Exa (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioExaComposioTool(ComposioPluginTool):
    """Exa."""

    name: str = 'exa_composio'
    display_name: str = 'Exa'
    description: str = 'Execute Exa actions via Composio.'
    app_name: str = 'exa'
