"""Contentful (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioContentfulComposioTool(ComposioPluginTool):
    """Contentful."""

    name: str = 'contentful_composio'
    display_name: str = 'Contentful'
    description: str = 'Execute Contentful actions via Composio.'
    app_name: str = 'contentful'
