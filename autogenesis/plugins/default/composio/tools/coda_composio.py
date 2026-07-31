"""Coda (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioCodaComposioTool(ComposioPluginTool):
    """Coda."""

    name: str = 'coda_composio'
    display_name: str = 'Coda'
    description: str = 'Execute Coda actions via Composio.'
    app_name: str = 'coda'
