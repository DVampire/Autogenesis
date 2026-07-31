"""Listennotes (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioListennotesComposioTool(ComposioPluginTool):
    """Listennotes."""

    name: str = 'listennotes_composio'
    display_name: str = 'Listennotes'
    description: str = 'Execute Listennotes actions via Composio.'
    app_name: str = 'listennotes'
