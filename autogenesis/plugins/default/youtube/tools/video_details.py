"""YouTube Video Details — info + statistics for a video (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase


class YoutubeVideoDetailsTool(YoutubeToolBase):
    """YouTube Video Details."""

    name: str = 'video_details'
    display_name: str = 'YouTube Video Details'
    description: str = 'Retrieves detailed information and statistics about YouTube videos.'

    async def __call__(self, video_url: str = "", api_key: str = "", include_statistics: bool = True,
                       include_content_details: bool = True, include_tags: bool = False, **kwargs) -> Response:
        video_url = str(video_url or "").strip()
        if not video_url:
            return self._fail("youtube.video_details: 'video_url' is required.")
        key = self._secret(api_key, "YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY")
        if not key:
            return self._fail("youtube.video_details: no API key (set api_key / YOUTUBE_API_KEY).")
        try:
            video_id = self._video_id(video_url)
        except ValueError as exc:
            return self._fail(f"youtube.video_details: {exc}")
        try:
            youtube = self._client(key)
            parts = ["snippet"]
            if include_statistics:
                parts.append("statistics")
            if include_content_details:
                parts.append("contentDetails")
            resp = youtube.videos().list(part=",".join(parts), id=video_id).execute()
            if not resp.get("items"):
                youtube.close()
                return self._fail(f"youtube.video_details: video not found for '{video_url}'.")
            info = resp["items"][0]
            snip = info["snippet"]
            row = {
                "video_id": video_id, "title": snip["title"], "description": snip["description"],
                "channel_title": snip["channelTitle"], "channel_id": snip["channelId"],
                "published_at": snip["publishedAt"], "url": f"https://www.youtube.com/watch?v={video_id}",
            }
            if include_tags:
                row["tags"] = snip.get("tags", [])
            if include_statistics and "statistics" in info:
                s = info["statistics"]
                row.update({
                    "view_count": int(s.get("viewCount", 0)),
                    "like_count": int(s.get("likeCount", 0)),
                    "comment_count": int(s.get("commentCount", 0)),
                })
            if include_content_details and "contentDetails" in info:
                cd = info["contentDetails"]
                row.update({"duration": cd.get("duration", ""),
                            "definition": cd.get("definition", "hd").upper(),
                            "has_captions": cd.get("caption", "false") == "true"})
            youtube.close()
            return self._ok(f"Retrieved details for '{row['title']}'.",
                            video_id=video_id, records=[row], count=1)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"youtube.video_details: {type(exc).__name__}: {exc}")
