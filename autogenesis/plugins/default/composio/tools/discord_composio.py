"""Discord (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioDiscordComposioTool(ComposioPluginTool):
    """Discord."""

    name: str = 'discord_composio'
    display_name: str = 'Discord'
    description: str = 'Execute Discord actions via Composio.'
    app_name: str = 'discord'
