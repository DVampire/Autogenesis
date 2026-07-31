"""VLM Run plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.transcription import VlmrunTranscriptionTool


@PLUGIN.register_module(force=True)
class VlmrunPlugin(Plugin):
    """VLM Run tools."""

    tools = (VlmrunTranscriptionTool,)

    name: str = 'vlmrun'
    display_name: str = 'VLM Run'
    description: str = 'VLM Run tools.'
    category: str = 'data'
    type: str = 'tool'
