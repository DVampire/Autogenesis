"""Supabase (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioSupabaseComposioTool(ComposioPluginTool):
    """Supabase."""

    name: str = 'supabase_composio'
    display_name: str = 'Supabase'
    description: str = 'Execute Supabase actions via Composio.'
    app_name: str = 'supabase'
