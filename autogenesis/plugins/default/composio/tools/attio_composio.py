"""Attio (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioAttioComposioTool(ComposioPluginTool):
    """Attio."""

    name: str = 'attio_composio'
    display_name: str = 'Attio'
    description: str = 'Execute Attio actions via Composio.'
    app_name: str = 'attio'
