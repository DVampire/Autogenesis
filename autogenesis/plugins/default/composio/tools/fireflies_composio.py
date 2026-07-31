"""Fireflies (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFirefliesComposioTool(ComposioPluginTool):
    """Fireflies."""

    name: str = 'fireflies_composio'
    display_name: str = 'Fireflies'
    description: str = 'Execute Fireflies actions via Composio.'
    app_name: str = 'fireflies'
