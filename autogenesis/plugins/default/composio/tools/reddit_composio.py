"""Reddit (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioRedditComposioTool(ComposioPluginTool):
    """Reddit."""

    name: str = 'reddit_composio'
    display_name: str = 'Reddit'
    description: str = 'Execute Reddit actions via Composio.'
    app_name: str = 'reddit'
