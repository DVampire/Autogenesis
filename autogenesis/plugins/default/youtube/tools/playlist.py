"""YouTube Playlist — extract all video URLs from a playlist (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase


class YoutubePlaylistTool(YoutubeToolBase):
    """YouTube Playlist."""

    name: str = 'playlist'
    display_name: str = 'YouTube Playlist'
    description: str = 'Extracts all video URLs from a YouTube playlist.'

    async def __call__(self, playlist_url: str = "", **kwargs) -> Response:
        playlist_url = str(playlist_url or "").strip()
        if not playlist_url:
            return self._fail("youtube.playlist: 'playlist_url' is required.")
        try:
            from pytube import Playlist

            playlist = Playlist(playlist_url)
            records = [{"video_url": url} for url in playlist.video_urls]
            return self._ok(f"Extracted {len(records)} video URLs from the playlist.",
                            playlist_url=playlist_url, records=records, count=len(records))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"youtube.playlist: {type(exc).__name__}: {exc}")
