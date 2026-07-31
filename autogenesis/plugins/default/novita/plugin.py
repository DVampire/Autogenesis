"""Novita AI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.novita import NovitaTool


@PLUGIN.register_module(force=True)
class NovitaPlugin(Plugin):
    """Novita AI tools."""

    tools = (NovitaTool,)

    name: str = 'novita'
    display_name: str = 'Novita AI'
    description: str = 'Novita AI tools.'
    category: str = 'data'
    type: str = 'model'
