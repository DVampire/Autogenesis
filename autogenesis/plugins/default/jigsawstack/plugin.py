"""JigsawStack plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.ai_scrape import JigsawstackAiScrapeTool
from .tools.ai_web_search import JigsawstackAiWebSearchTool
from .tools.file_read import JigsawstackFileReadTool
from .tools.file_upload import JigsawstackFileUploadTool
from .tools.image_generation import JigsawstackImageGenerationTool
from .tools.nsfw import JigsawstackNsfwTool
from .tools.object_detection import JigsawstackObjectDetectionTool
from .tools.sentiment import JigsawstackSentimentTool
from .tools.text_to_sql import JigsawstackTextToSqlTool
from .tools.text_translate import JigsawstackTextTranslateTool
from .tools.vocr import JigsawstackVocrTool


@PLUGIN.register_module(force=True)
class JigsawstackPlugin(Plugin):
    """JigsawStack tools."""

    tools = (
        JigsawstackAiScrapeTool,
        JigsawstackAiWebSearchTool,
        JigsawstackFileReadTool,
        JigsawstackFileUploadTool,
        JigsawstackImageGenerationTool,
        JigsawstackNsfwTool,
        JigsawstackObjectDetectionTool,
        JigsawstackSentimentTool,
        JigsawstackTextToSqlTool,
        JigsawstackTextTranslateTool,
        JigsawstackVocrTool,
    )

    name: str = 'jigsawstack'
    display_name: str = 'JigsawStack'
    description: str = 'JigsawStack tools.'
    category: str = 'data'
    type: str = 'tool'
