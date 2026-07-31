"""ElevenLabs (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioElevenlabsComposioTool(ComposioPluginTool):
    """ElevenLabs."""

    name: str = 'elevenlabs_composio'
    display_name: str = 'ElevenLabs'
    description: str = 'Execute ElevenLabs actions via Composio.'
    app_name: str = 'elevenlabs'
