"""GitHub (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioGithubComposioTool(ComposioPluginTool):
    """GitHub."""

    name: str = 'github_composio'
    display_name: str = 'GitHub'
    description: str = 'Execute GitHub actions via Composio.'
    app_name: str = 'github'
