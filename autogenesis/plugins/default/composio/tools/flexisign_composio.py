"""Flexisign (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioFlexisignComposioTool(ComposioPluginTool):
    """Flexisign."""

    name: str = 'flexisign_composio'
    display_name: str = 'Flexisign'
    description: str = 'Execute Flexisign actions via Composio.'
    app_name: str = 'flexisign'
