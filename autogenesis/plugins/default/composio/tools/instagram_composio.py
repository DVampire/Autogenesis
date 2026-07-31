"""Instagram (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioInstagramComposioTool(ComposioPluginTool):
    """Instagram."""

    name: str = 'instagram_composio'
    display_name: str = 'Instagram'
    description: str = 'Execute Instagram actions via Composio.'
    app_name: str = 'instagram'
