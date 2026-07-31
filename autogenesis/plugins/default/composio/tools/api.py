"""Composio API — generic Composio action executor (ported)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioApiTool(ComposioPluginTool):
    """Composio API."""

    name: str = 'composio_api'
    display_name: str = 'Composio API'
    description: str = 'Execute any Composio action across connected apps.'
    app_name: str = 'composio'
