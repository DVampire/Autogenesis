"""Apify plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.actor import ApifyActorTool


@PLUGIN.register_module(force=True)
class ApifyPlugin(Plugin):
    """Apify tools."""

    tools = (ApifyActorTool,)

    name: str = 'apify'
    display_name: str = 'Apify'
    description: str = 'Apify tools.'
    category: str = 'data'
    type: str = 'tool'
