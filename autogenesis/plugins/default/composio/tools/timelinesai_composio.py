"""TimelinesAI (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioTimelinesaiComposioTool(ComposioPluginTool):
    """TimelinesAI."""

    name: str = 'timelinesai_composio'
    display_name: str = 'TimelinesAI'
    description: str = 'Execute TimelinesAI actions via Composio.'
    app_name: str = 'timelinesai'
