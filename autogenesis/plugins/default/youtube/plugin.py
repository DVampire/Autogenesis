"""YouTube plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.channel import YoutubeChannelTool
from .tools.comments import YoutubeCommentsTool
from .tools.playlist import YoutubePlaylistTool
from .tools.search import YoutubeSearchTool
from .tools.transcripts import YoutubeTranscriptsTool
from .tools.trending import YoutubeTrendingTool
from .tools.video_details import YoutubeVideoDetailsTool


@PLUGIN.register_module(force=True)
class YoutubePlugin(Plugin):
    """YouTube tools."""

    tools = (
        YoutubeChannelTool,
        YoutubeCommentsTool,
        YoutubePlaylistTool,
        YoutubeSearchTool,
        YoutubeTrendingTool,
        YoutubeVideoDetailsTool,
        YoutubeTranscriptsTool,
    )

    name: str = 'youtube'
    display_name: str = 'YouTube'
    description: str = 'YouTube tools.'
    category: str = 'data'
    type: str = 'data_source'
