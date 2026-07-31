"""CometAPI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.cometapi import CometapiTool


@PLUGIN.register_module(force=True)
class CometapiPlugin(Plugin):
    """CometAPI tools."""

    tools = (CometapiTool,)

    name: str = 'cometapi'
    display_name: str = 'CometAPI'
    description: str = 'CometAPI tools.'
    category: str = 'data'
    type: str = 'model'
