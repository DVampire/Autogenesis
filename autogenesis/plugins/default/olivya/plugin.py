"""Olivya plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.olivya import OlivyaTool


@PLUGIN.register_module(force=True)
class OlivyaPlugin(Plugin):
    """Olivya tools."""

    tools = (OlivyaTool,)

    name: str = 'olivya'
    display_name: str = 'Olivya'
    description: str = 'Olivya tools.'
    category: str = 'data'
    type: str = 'tool'
