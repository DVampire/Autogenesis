"""GoogleDocs (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGoogledocsComposioTool(ComposioPluginTool):
    """GoogleDocs."""

    name: str = 'googledocs_composio'
    display_name: str = 'GoogleDocs'
    description: str = 'Execute GoogleDocs actions via Composio.'
    app_name: str = 'googledocs'
