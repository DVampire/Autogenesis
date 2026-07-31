"""xAI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.xai import XaiTool


@PLUGIN.register_module(force=True)
class XaiPlugin(Plugin):
    """xAI tools."""

    tools = (XaiTool,)

    name: str = 'xai'
    display_name: str = 'xAI'
    description: str = 'xAI tools.'
    category: str = 'data'
    type: str = 'model'
