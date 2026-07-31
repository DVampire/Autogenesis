"""TwelveLabs plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.convert_astra_results import TwelvelabsConvertAstraResultsTool
from .tools.pegasus import TwelvelabsPegasusTool
from .tools.pegasus_index import TwelvelabsPegasusIndexTool
from .tools.split_video import TwelvelabsSplitVideoTool
from .tools.text_embeddings import TwelvelabsTextEmbeddingsTool
from .tools.video_embeddings import TwelvelabsVideoEmbeddingsTool
from .tools.video_file import TwelvelabsVideoFileTool


@PLUGIN.register_module(force=True)
class TwelvelabsPlugin(Plugin):
    """TwelveLabs tools."""

    tools = (
        TwelvelabsConvertAstraResultsTool,
        TwelvelabsPegasusIndexTool,
        TwelvelabsSplitVideoTool,
        TwelvelabsTextEmbeddingsTool,
        TwelvelabsPegasusTool,
        TwelvelabsVideoEmbeddingsTool,
        TwelvelabsVideoFileTool,
    )

    name: str = 'twelvelabs'
    display_name: str = 'TwelveLabs'
    description: str = 'TwelveLabs tools.'
    category: str = 'data'
    type: str = 'tool'
