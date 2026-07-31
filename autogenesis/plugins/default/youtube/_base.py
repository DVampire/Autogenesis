"""Shared helpers for the YouTube provider tools (ported from Langflow).

Keeps the YouTube Data API client + video-id extraction in one place so each
tool module stays a thin ``__call__``. The API key resolves from the call arg,
the ``youtube_plugin`` config block, or ``YOUTUBE_API_KEY`` (see
:meth:`PluginTool._secret`).
"""

from __future__ import annotations

import re

from autogenesis.plugins.types import PluginTool

# Canonical YouTube URL → video-id patterns (verbatim from Langflow).
_VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)",
    r"youtube\.com\/watch\?.*?v=([^&\n?#]+)",
]


class YoutubeToolBase(PluginTool):
    """Base for YouTube provider tools — client factory + id extraction."""

    def _client(self, api_key: str):
        """Build a YouTube Data API v3 client (needs ``google-api-python-client``)."""
        from googleapiclient.discovery import build

        return build("youtube", "v3", developerKey=api_key)

    @staticmethod
    def _video_id(url: str) -> str:
        for pattern in _VIDEO_ID_PATTERNS:
            match = re.search(pattern, url or "")
            if match:
                return match.group(1)
        raise ValueError(f"Could not extract video ID from URL: {url}")
