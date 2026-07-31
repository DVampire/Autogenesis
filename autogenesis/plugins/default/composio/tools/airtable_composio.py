"""Airtable (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioAirtableComposioTool(ComposioPluginTool):
    """Airtable."""

    name: str = 'airtable_composio'
    display_name: str = 'Airtable'
    description: str = 'Execute Airtable actions via Composio.'
    app_name: str = 'airtable'
