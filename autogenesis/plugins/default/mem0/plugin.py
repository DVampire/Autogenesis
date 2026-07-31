"""Mem0 plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chat_memory import Mem0ChatMemoryTool


@PLUGIN.register_module(force=True)
class Mem0Plugin(Plugin):
    """Mem0 tools."""

    tools = (Mem0ChatMemoryTool,)

    name: str = 'mem0'
    display_name: str = 'Mem0'
    description: str = 'Mem0 tools.'
    category: str = 'agent'
    type: str = 'memory'
