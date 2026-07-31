"""Pandadoc (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioPandadocComposioTool(ComposioPluginTool):
    """Pandadoc."""

    name: str = 'pandadoc_composio'
    display_name: str = 'Pandadoc'
    description: str = 'Execute Pandadoc actions via Composio.'
    app_name: str = 'pandadoc'
