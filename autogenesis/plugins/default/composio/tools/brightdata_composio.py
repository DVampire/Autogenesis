"""Brightdata (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioBrightdataComposioTool(ComposioPluginTool):
    """Brightdata."""

    name: str = 'brightdata_composio'
    display_name: str = 'Brightdata'
    description: str = 'Execute Brightdata actions via Composio.'
    app_name: str = 'brightdata'
