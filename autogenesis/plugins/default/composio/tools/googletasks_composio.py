"""GoogleTasks (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGoogletasksComposioTool(ComposioPluginTool):
    """GoogleTasks."""

    name: str = 'googletasks_composio'
    display_name: str = 'GoogleTasks'
    description: str = 'Execute GoogleTasks actions via Composio.'
    app_name: str = 'googletasks'
