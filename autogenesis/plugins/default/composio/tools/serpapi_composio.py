"""SerpAPI (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioSerpapiComposioTool(ComposioPluginTool):
    """SerpAPI."""

    name: str = 'serpapi_composio'
    display_name: str = 'SerpAPI'
    description: str = 'Execute SerpAPI actions via Composio.'
    app_name: str = 'serpapi'
