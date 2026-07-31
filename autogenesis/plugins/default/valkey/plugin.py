"""Valkey plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chat import ValkeyChatTool
from .tools.valkey import ValkeyTool


@PLUGIN.register_module(force=True)
class ValkeyPlugin(Plugin):
    """Valkey tools."""

    tools = (ValkeyTool, ValkeyChatTool,)

    name: str = 'valkey'
    display_name: str = 'Valkey'
    description: str = 'Valkey tools.'
    category: str = 'data'
    type: str = 'vectorstore'
