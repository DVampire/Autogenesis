"""OpenRouter plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.openrouter import OpenrouterTool


@PLUGIN.register_module(force=True)
class OpenrouterPlugin(Plugin):
    """OpenRouter tools."""

    tools = (OpenrouterTool,)

    name: str = 'openrouter'
    display_name: str = 'OpenRouter'
    description: str = 'OpenRouter tools.'
    category: str = 'data'
    type: str = 'model'
