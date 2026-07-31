"""GoogleBigQuery (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGooglebigqueryComposioTool(ComposioPluginTool):
    """GoogleBigQuery."""

    name: str = 'googlebigquery_composio'
    display_name: str = 'GoogleBigQuery'
    description: str = 'Execute GoogleBigQuery actions via Composio.'
    app_name: str = 'googlebigquery'
