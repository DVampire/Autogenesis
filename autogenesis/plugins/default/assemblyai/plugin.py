"""AssemblyAI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.get_subtitles import AssemblyaiGetSubtitlesTool
from .tools.lemur import AssemblyaiLemurTool
from .tools.list_transcripts import AssemblyaiListTranscriptsTool
from .tools.poll_transcript import AssemblyaiPollTranscriptTool
from .tools.start_transcript import AssemblyaiStartTranscriptTool


@PLUGIN.register_module(force=True)
class AssemblyaiPlugin(Plugin):
    """AssemblyAI tools."""

    tools = (
        AssemblyaiGetSubtitlesTool,
        AssemblyaiLemurTool,
        AssemblyaiListTranscriptsTool,
        AssemblyaiPollTranscriptTool,
        AssemblyaiStartTranscriptTool,
    )

    name: str = 'assemblyai'
    display_name: str = 'AssemblyAI'
    description: str = 'AssemblyAI tools.'
    category: str = 'data'
    type: str = 'tool'
