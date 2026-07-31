"""Linear (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioLinearComposioTool(ComposioPluginTool):
    """Linear."""

    name: str = 'linear_composio'
    display_name: str = 'Linear'
    description: str = 'Execute Linear actions via Composio.'
    app_name: str = 'linear'
