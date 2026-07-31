"""WolframAlpha plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.wolfram_alpha_api import WolframalphaWolframAlphaApiTool


@PLUGIN.register_module(force=True)
class WolframalphaPlugin(Plugin):
    """WolframAlpha tools."""

    tools = (WolframalphaWolframAlphaApiTool,)

    name: str = 'wolframalpha'
    display_name: str = 'WolframAlpha'
    description: str = 'WolframAlpha tools.'
    category: str = 'data'
    type: str = 'tool'
