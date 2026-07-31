"""Tavily (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioTavilyComposioTool(ComposioPluginTool):
    """Tavily."""

    name: str = 'tavily_composio'
    display_name: str = 'Tavily'
    description: str = 'Execute Tavily actions via Composio.'
    app_name: str = 'tavily'
