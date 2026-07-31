"""Fixer (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFixerComposioTool(ComposioPluginTool):
    """Fixer."""

    name: str = 'fixer_composio'
    display_name: str = 'Fixer'
    description: str = 'Execute Fixer actions via Composio.'
    app_name: str = 'fixer'
