"""Supabase plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.supabase import SupabaseTool


@PLUGIN.register_module(force=True)
class SupabasePlugin(Plugin):
    """Supabase tools."""

    tools = (SupabaseTool,)

    name: str = 'supabase'
    display_name: str = 'Supabase'
    description: str = 'Supabase tools.'
    category: str = 'data'
    type: str = 'vectorstore'
