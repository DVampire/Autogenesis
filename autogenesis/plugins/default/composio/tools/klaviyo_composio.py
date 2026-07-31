"""Klaviyo (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioKlaviyoComposioTool(ComposioPluginTool):
    """Klaviyo."""

    name: str = 'klaviyo_composio'
    display_name: str = 'Klaviyo'
    description: str = 'Execute Klaviyo actions via Composio.'
    app_name: str = 'klaviyo'
