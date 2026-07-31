"""GoogleCalendar (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGooglecalendarComposioTool(ComposioPluginTool):
    """GoogleCalendar."""

    name: str = 'googlecalendar_composio'
    display_name: str = 'GoogleCalendar'
    description: str = 'Execute GoogleCalendar actions via Composio.'
    app_name: str = 'googlecalendar'
