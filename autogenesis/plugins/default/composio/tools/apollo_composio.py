"""Apollo (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioApolloComposioTool(ComposioPluginTool):
    """Apollo."""

    name: str = 'apollo_composio'
    display_name: str = 'Apollo'
    description: str = 'Execute Apollo actions via Composio.'
    app_name: str = 'apollo'
