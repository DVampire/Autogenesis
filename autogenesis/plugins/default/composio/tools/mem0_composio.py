"""Mem0 (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioMem0ComposioTool(ComposioPluginTool):
    """Mem0."""

    name: str = 'mem0_composio'
    display_name: str = 'Mem0'
    description: str = 'Execute Mem0 actions via Composio.'
    app_name: str = 'mem0'
