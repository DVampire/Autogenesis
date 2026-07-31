"""PerplexityAI (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioPerplexityaiComposioTool(ComposioPluginTool):
    """PerplexityAI."""

    name: str = 'perplexityai_composio'
    display_name: str = 'PerplexityAI'
    description: str = 'Execute PerplexityAI actions via Composio.'
    app_name: str = 'perplexityai'
