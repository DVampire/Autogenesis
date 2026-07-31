"""SambaNova plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.sambanova import SambanovaTool


@PLUGIN.register_module(force=True)
class SambanovaPlugin(Plugin):
    """SambaNova tools."""

    tools = (SambanovaTool,)

    name: str = 'sambanova'
    display_name: str = 'SambaNova'
    description: str = 'SambaNova tools.'
    category: str = 'data'
    type: str = 'model'
