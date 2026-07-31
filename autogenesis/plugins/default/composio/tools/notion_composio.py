"""Notion (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioNotionComposioTool(ComposioPluginTool):
    """Notion."""

    name: str = 'notion_composio'
    display_name: str = 'Notion'
    description: str = 'Execute Notion actions via Composio.'
    app_name: str = 'notion'
