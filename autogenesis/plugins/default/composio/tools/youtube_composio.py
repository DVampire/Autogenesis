"""YouTube (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioYoutubeComposioTool(ComposioPluginTool):
    """YouTube."""

    name: str = 'youtube_composio'
    display_name: str = 'YouTube'
    description: str = 'Execute YouTube actions via Composio.'
    app_name: str = 'youtube'
