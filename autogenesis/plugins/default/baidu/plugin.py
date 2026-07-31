"""Qianfan plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.qianfan_chat import BaiduQianfanChatTool


@PLUGIN.register_module(force=True)
class BaiduPlugin(Plugin):
    """Qianfan tools."""

    tools = (BaiduQianfanChatTool,)

    name: str = 'baidu'
    display_name: str = 'Qianfan'
    description: str = 'Qianfan tools.'
    category: str = 'data'
    type: str = 'model'
