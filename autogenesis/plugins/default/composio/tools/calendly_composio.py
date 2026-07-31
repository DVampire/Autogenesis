"""Calendly (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioCalendlyComposioTool(ComposioPluginTool):
    """Calendly."""

    name: str = 'calendly_composio'
    display_name: str = 'Calendly'
    description: str = 'Execute Calendly actions via Composio.'
    app_name: str = 'calendly'
