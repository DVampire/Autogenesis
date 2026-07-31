"""Google Classroom (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGoogleclassroomComposioTool(ComposioPluginTool):
    """Google Classroom."""

    name: str = 'googleclassroom_composio'
    display_name: str = 'Google Classroom'
    description: str = 'Execute Google Classroom actions via Composio.'
    app_name: str = 'GOOGLE_CLASSROOM'
