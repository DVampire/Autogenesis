"""Hugging Face plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.huggingface import HuggingfaceTool
from .tools.inference_api import HuggingfaceInferenceApiTool


@PLUGIN.register_module(force=True)
class HuggingfacePlugin(Plugin):
    """Hugging Face tools."""

    tools = (HuggingfaceTool, HuggingfaceInferenceApiTool,)

    name: str = 'huggingface'
    display_name: str = 'Hugging Face'
    description: str = 'Hugging Face tools.'
    category: str = 'data'
    type: str = 'model'
