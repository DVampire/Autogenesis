"""Needle plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.needle import NeedleTool


@PLUGIN.register_module(force=True)
class NeedlePlugin(Plugin):
    """Needle tools."""

    tools = (NeedleTool,)

    name: str = 'needle'
    display_name: str = 'Needle'
    description: str = 'Needle tools.'
    category: str = 'data'
    type: str = 'vectorstore'
