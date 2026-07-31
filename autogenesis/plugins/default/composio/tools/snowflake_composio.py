"""Snowflake (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioSnowflakeComposioTool(ComposioPluginTool):
    """Snowflake."""

    name: str = 'snowflake_composio'
    display_name: str = 'Snowflake'
    description: str = 'Execute Snowflake actions via Composio.'
    app_name: str = 'snowflake'
