"""Firecrawl (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFirecrawlComposioTool(ComposioPluginTool):
    """Firecrawl."""

    name: str = 'firecrawl_composio'
    display_name: str = 'Firecrawl'
    description: str = 'Execute Firecrawl actions via Composio.'
    app_name: str = 'firecrawl'
