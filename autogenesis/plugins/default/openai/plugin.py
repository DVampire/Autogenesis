"""OpenAI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chat_model import OpenaiChatModelTool
from .tools.openai import OpenaiTool


@PLUGIN.register_module(force=True)
class OpenaiPlugin(Plugin):
    """OpenAI tools."""

    tools = (OpenaiTool, OpenaiChatModelTool,)

    name: str = 'openai'
    display_name: str = 'OpenAI'
    description: str = 'OpenAI tools.'
    category: str = 'data'
    type: str = 'embedding'
