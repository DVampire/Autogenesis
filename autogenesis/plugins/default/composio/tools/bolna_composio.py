"""Bolna (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioBolnaComposioTool(ComposioPluginTool):
    """Bolna."""

    name: str = 'bolna_composio'
    display_name: str = 'Bolna'
    description: str = 'Execute Bolna actions via Composio.'
    app_name: str = 'bolna'
