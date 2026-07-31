"""Heygen (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioHeygenComposioTool(ComposioPluginTool):
    """Heygen."""

    name: str = 'heygen_composio'
    display_name: str = 'Heygen'
    description: str = 'Execute Heygen actions via Composio.'
    app_name: str = 'heygen'
