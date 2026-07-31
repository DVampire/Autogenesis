"""PeopleDataLabs (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioPeopledatalabsComposioTool(ComposioPluginTool):
    """PeopleDataLabs."""

    name: str = 'peopledatalabs_composio'
    display_name: str = 'PeopleDataLabs'
    description: str = 'Execute PeopleDataLabs actions via Composio.'
    app_name: str = 'peopledatalabs'
