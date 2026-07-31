"""LiteLLM Proxy plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.proxy import LitellmProxyTool


@PLUGIN.register_module(force=True)
class LitellmPlugin(Plugin):
    """LiteLLM Proxy tools."""

    tools = (LitellmProxyTool,)

    name: str = 'litellm'
    display_name: str = 'LiteLLM Proxy'
    description: str = 'LiteLLM Proxy tools.'
    category: str = 'data'
    type: str = 'model'
