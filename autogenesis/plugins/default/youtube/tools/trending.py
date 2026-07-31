"""YouTube Trending — most-popular videos by region/category (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase

_COUNTRY = {
    "Global": "US", "United States": "US", "Brazil": "BR", "United Kingdom": "GB",
    "India": "IN", "Japan": "JP", "South Korea": "KR", "Germany": "DE", "France": "FR",
    "Canada": "CA", "Australia": "AU", "Spain": "ES", "Italy": "IT", "Mexico": "MX",
    "Russia": "RU", "Netherlands": "NL", "Poland": "PL", "Argentina": "AR",
}
_CATEGORY = {
    "All": "0", "Film & Animation": "1", "Autos & Vehicles": "2", "Music": "10",
    "Pets & Animals": "15", "Sports": "17", "Travel & Events": "19", "Gaming": "20",
    "People & Blogs": "22", "Comedy": "23", "Entertainment": "24", "News & Politics": "25",
    "Education": "27", "Science & Technology": "28", "Nonprofits & Activism": "29",
}
_MAX = 50


class YoutubeTrendingTool(YoutubeToolBase):
    """YouTube Trending."""

    name: str = 'trending'
    display_name: str = 'YouTube Trending'
    description: str = 'Retrieves trending videos from YouTube with filtering options.'

    async def __call__(self, api_key: str = "", region: str = "Global", category: str = "All",
                       max_results: int = 10, include_statistics: bool = True, **kwargs) -> Response:
        key = self._secret(api_key, "YOUTUBE_API_KEY", "YOUTUBE_DATA_API_KEY")
        if not key:
            return self._fail("youtube.trending: no API key (set api_key / YOUTUBE_API_KEY).")
        max_results = min(max(1, int(max_results)), _MAX)
        try:
            youtube = self._client(key)
            parts = ["snippet"] + (["statistics"] if include_statistics else [])
            params = {"part": ",".join(parts), "chart": "mostPopular",
                      "regionCode": _COUNTRY.get(region, "US"), "maxResults": max_results}
            if category != "All":
                params["videoCategoryId"] = _CATEGORY.get(category, "0")
            resp = youtube.videos().list(**params).execute()
            records = []
            for item in resp.get("items", []):
                row = {
                    "video_id": item["id"], "title": item["snippet"]["title"],
                    "channel_title": item["snippet"]["channelTitle"],
                    "published_at": item["snippet"]["publishedAt"],
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "region": region, "category": category,
                }
                if include_statistics and "statistics" in item:
                    s = item["statistics"]
                    row.update({
                        "view_count": int(s.get("viewCount", 0)),
                        "like_count": int(s.get("likeCount", 0)),
                        "comment_count": int(s.get("commentCount", 0)),
                    })
                records.append(row)
            youtube.close()
            return self._ok(f"Retrieved {len(records)} trending videos ({region}/{category}).",
                            region=region, category=category, records=records, count=len(records))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"youtube.trending: {type(exc).__name__}: {exc}")
