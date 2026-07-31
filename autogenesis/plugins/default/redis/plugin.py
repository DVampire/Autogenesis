"""Redis plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.chat import RedisChatTool
from .tools.redis import RedisTool


@PLUGIN.register_module(force=True)
class RedisPlugin(Plugin):
    """Redis tools."""

    tools = (RedisTool, RedisChatTool,)

    name: str = 'redis'
    display_name: str = 'Redis'
    description: str = 'Redis tools.'
    category: str = 'data'
    type: str = 'vectorstore'
