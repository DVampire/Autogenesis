"""Upstash plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.upstash import UpstashTool


@PLUGIN.register_module(force=True)
class UpstashPlugin(Plugin):
    """Upstash tools."""

    tools = (UpstashTool,)

    name: str = 'upstash'
    display_name: str = 'Upstash'
    description: str = 'Upstash tools.'
    category: str = 'data'
    type: str = 'vectorstore'
