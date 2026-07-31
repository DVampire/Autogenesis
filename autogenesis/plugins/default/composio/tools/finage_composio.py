"""Finage (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFinageComposioTool(ComposioPluginTool):
    """Finage."""

    name: str = 'finage_composio'
    display_name: str = 'Finage'
    description: str = 'Execute Finage actions via Composio.'
    app_name: str = 'finage'
