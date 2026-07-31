"""Canva (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioCanvaComposioTool(ComposioPluginTool):
    """Canva."""

    name: str = 'canva_composio'
    display_name: str = 'Canva'
    description: str = 'Execute Canva actions via Composio.'
    app_name: str = 'canva'
