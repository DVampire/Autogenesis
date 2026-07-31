"""YouTube Search — search videos by query (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase


class YoutubeSearchTool(YoutubeToolBase):
    """YouTube Search."""

    name: str = 'search'
    display_name: str = 'YouTube Search'
    description: str = 'Searches YouTube videos based on query.'

    async def __call__(self, query: str = "", api_key: str = "", max_results: int = 10,
                       order: str = "relevance", include_metadata: bool = True, **kwargs) -> Response:
        query = str(query or "").strip()
        if not query:
            return self._fail("youtube.search: 'query' is required.")
        key = self._secret(api_key, "YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY")
        if not key:
            return self._fail("youtube.search: no API key (set api_key / YOUTUBE_API_KEY).")
        try:
            youtube = self._client(key)
            resp = youtube.search().list(
                q=query, part="id,snippet", maxResults=int(max_results),
                order=order, type="video",
            ).execute()
            records = []
            for item in resp.get("items", []):
                vid = item["id"]["videoId"]
                snip = item["snippet"]
                row = {
                    "video_id": vid, "title": snip["title"], "description": snip["description"],
                    "published_at": snip["publishedAt"], "channel_title": snip["channelTitle"],
                    "thumbnail_url": snip["thumbnails"]["default"]["url"],
                    "url": f"https://www.youtube.com/watch?v={vid}",
                }
                if include_metadata:
                    det = youtube.videos().list(part="statistics,contentDetails", id=vid).execute()
                    if det.get("items"):
                        d = det["items"][0]
                        row.update({
                            "view_count": int(d["statistics"].get("viewCount", 0)),
                            "like_count": int(d["statistics"].get("likeCount", 0)),
                            "comment_count": int(d["statistics"].get("commentCount", 0)),
                            "duration": d["contentDetails"]["duration"],
                        })
                records.append(row)
            youtube.close()
            return self._ok(f"Found {len(records)} videos for '{query}'.",
                            query=query, records=records, count=len(records))
        except Exception as exc:  # noqa: BLE001 — provider/network error is a failed result
            return self._fail(f"youtube.search: {type(exc).__name__}: {exc}")
