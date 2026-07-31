"""YouTube Comments — fetch a video's comment threads (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase

_API_MAX = 100


class YoutubeCommentsTool(YoutubeToolBase):
    """YouTube Comments."""

    name: str = 'comments'
    display_name: str = 'YouTube Comments'
    description: str = 'Retrieves and analyzes comments from YouTube videos.'

    @staticmethod
    def _process(item: dict, *, include_metrics: bool, include_replies: bool) -> list[dict]:
        snip = item["snippet"]["topLevelComment"]["snippet"]
        cid = item["snippet"]["topLevelComment"]["id"]
        rows = [{
            "comment_id": cid, "parent_comment_id": "", "is_reply": False,
            "author": snip["authorDisplayName"], "author_channel_url": snip.get("authorChannelUrl", ""),
            "text": snip["textDisplay"], "published_at": snip["publishedAt"], "updated_at": snip["updatedAt"],
        }]
        if include_metrics:
            rows[0].update({"like_count": snip["likeCount"], "reply_count": item["snippet"]["totalReplyCount"]})
        if include_replies and item["snippet"]["totalReplyCount"] > 0 and "replies" in item:
            for reply in item["replies"]["comments"]:
                rs = reply["snippet"]
                row = {
                    "comment_id": reply["id"], "parent_comment_id": cid, "is_reply": True,
                    "author": rs["authorDisplayName"], "author_channel_url": rs.get("authorChannelUrl", ""),
                    "text": rs["textDisplay"], "published_at": rs["publishedAt"], "updated_at": rs["updatedAt"],
                }
                if include_metrics:
                    row.update({"like_count": rs["likeCount"], "reply_count": 0})
                rows.append(row)
        return rows

    async def __call__(self, video_url: str = "", api_key: str = "", max_results: int = 20,
                       sort_by: str = "relevance", include_metrics: bool = True,
                       include_replies: bool = False, **kwargs) -> Response:
        video_url = str(video_url or "").strip()
        if not video_url:
            return self._fail("youtube.comments: 'video_url' is required.")
        key = self._secret(api_key, "YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY")
        if not key:
            return self._fail("youtube.comments: no API key (set api_key / YOUTUBE_API_KEY).")
        try:
            video_id = self._video_id(video_url)
        except ValueError as exc:
            return self._fail(f"youtube.comments: {exc}")
        max_results = int(max_results)
        try:
            youtube = self._client(key)
            records: list[dict] = []
            count = 0
            request = youtube.commentThreads().list(
                part="snippet,replies", videoId=video_id,
                maxResults=min(_API_MAX, max_results), order=sort_by, textFormat="plainText")
            while request and count < max_results:
                resp = request.execute()
                for item in resp.get("items", []):
                    if count >= max_results:
                        break
                    for row in self._process(item, include_metrics=include_metrics, include_replies=include_replies):
                        row.update({"video_id": video_id, "video_url": video_url})
                        records.append(row)
                    count += 1
                token = resp.get("nextPageToken")
                if token and count < max_results:
                    request = youtube.commentThreads().list(
                        part="snippet,replies", videoId=video_id,
                        maxResults=min(_API_MAX, max_results - count), order=sort_by,
                        textFormat="plainText", pageToken=token)
                else:
                    request = None
            youtube.close()
            return self._ok(f"Fetched {len(records)} comments for video '{video_id}'.",
                            video_id=video_id, video_url=video_url, records=records, count=len(records))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"youtube.comments: {type(exc).__name__}: {exc}")
