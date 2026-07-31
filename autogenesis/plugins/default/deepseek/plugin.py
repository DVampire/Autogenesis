"""DeepSeek plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.deepseek import DeepseekTool


@PLUGIN.register_module(force=True)
class DeepseekPlugin(Plugin):
    """DeepSeek tools."""

    tools = (DeepseekTool,)

    name: str = 'deepseek'
    display_name: str = 'DeepSeek'
    description: str = 'DeepSeek tools.'
    category: str = 'data'
    type: str = 'model'
