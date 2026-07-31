"""GoogleSheets (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGooglesheetsComposioTool(ComposioPluginTool):
    """GoogleSheets."""

    name: str = 'googlesheets_composio'
    display_name: str = 'GoogleSheets'
    description: str = 'Execute GoogleSheets actions via Composio.'
    app_name: str = 'googlesheets'
