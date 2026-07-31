"""Todoist (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioTodoistComposioTool(ComposioPluginTool):
    """Todoist."""

    name: str = 'todoist_composio'
    display_name: str = 'Todoist'
    description: str = 'Execute Todoist actions via Composio.'
    app_name: str = 'todoist'
