"""PaddleOCR plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.paddleocr import PaddleocrTool


@PLUGIN.register_module(force=True)
class PaddlePlugin(Plugin):
    """PaddleOCR tools."""

    tools = (PaddleocrTool,)

    name: str = 'paddle'
    display_name: str = 'PaddleOCR'
    description: str = 'PaddleOCR tools.'
    category: str = 'data'
    type: str = 'tool'
