"""YouTube Channel — channel info + statistics (ported from Langflow)."""

import re

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase

_URL_PATTERNS = {
    "custom_url": r"youtube\.com\/c\/([^\/\n?]+)",
    "channel_id": r"youtube\.com\/channel\/([^\/\n?]+)",
    "user": r"youtube\.com\/user\/([^\/\n?]+)",
    "handle": r"youtube\.com\/@([^\/\n?]+)",
}


class YoutubeChannelTool(YoutubeToolBase):
    """YouTube Channel."""

    name: str = 'channel'
    display_name: str = 'YouTube Channel'
    description: str = 'Retrieves detailed information and statistics about YouTube channels.'

    def _channel_id(self, youtube, channel_url: str) -> str:
        if channel_url.startswith("UC") and len(channel_url) == 24:
            return channel_url
        for kind, pattern in _URL_PATTERNS.items():
            match = re.search(pattern, channel_url)
            if match:
                if kind == "channel_id":
                    return match.group(1)
                resp = youtube.search().list(part="id", q=match.group(1), type="channel", maxResults=1).execute()
                if resp.get("items"):
                    return resp["items"][0]["id"]["channelId"]
        return channel_url

    async def __call__(self, channel_url: str = "", api_key: str = "",
                       include_statistics: bool = True, include_branding: bool = False, **kwargs) -> Response:
        channel_url = str(channel_url or "").strip()
        if not channel_url:
            return self._fail("youtube.channel: 'channel_url' is required.")
        key = self._secret(api_key, "YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY")
        if not key:
            return self._fail("youtube.channel: no API key (set api_key / YOUTUBE_API_KEY).")
        try:
            youtube = self._client(key)
            channel_id = self._channel_id(youtube, channel_url)
            parts = ["snippet", "contentDetails"]
            if include_statistics:
                parts.append("statistics")
            if include_branding:
                parts.append("brandingSettings")
            resp = youtube.channels().list(part=",".join(parts), id=channel_id).execute()
            if not resp.get("items"):
                youtube.close()
                return self._fail(f"youtube.channel: channel not found for '{channel_url}'.")
            info = resp["items"][0]
            snip = info["snippet"]
            row = {
                "title": snip["title"], "description": snip["description"],
                "custom_url": snip.get("customUrl", ""), "published_at": snip["publishedAt"],
                "country": snip.get("country", "Not specified"), "channel_id": channel_id,
            }
            if include_statistics:
                s = info.get("statistics", {})
                row.update({
                    "view_count": int(s.get("viewCount", 0)),
                    "subscriber_count": int(s.get("subscriberCount", 0)),
                    "video_count": int(s.get("videoCount", 0)),
                })
            if include_branding:
                brand = info.get("brandingSettings", {}).get("channel", {})
                row.update({"brand_title": brand.get("title", ""), "brand_keywords": brand.get("keywords", "")})
            youtube.close()
            return self._ok(f"Retrieved channel info for '{row['title']}'.",
                            channel_id=channel_id, records=[row], count=1)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"youtube.channel: {type(exc).__name__}: {exc}")
