"""Dropbox (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioDropboxCompnentTool(ComposioPluginTool):
    """Dropbox."""

    name: str = 'dropbox_compnent'
    display_name: str = 'Dropbox'
    description: str = 'Execute Dropbox actions via Composio.'
    app_name: str = 'dropbox'
