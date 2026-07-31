"""Bitbucket (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioBitbucketComposioTool(ComposioPluginTool):
    """Bitbucket."""

    name: str = 'bitbucket_composio'
    display_name: str = 'Bitbucket'
    description: str = 'Execute Bitbucket actions via Composio.'
    app_name: str = 'bitbucket'
