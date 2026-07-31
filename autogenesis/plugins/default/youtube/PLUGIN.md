---
id: youtube
name: YouTube
category: data
type: data_source
icon: resources/icon.svg
tools: 7
implemented: 7
credentials: [YOUTUBE_API_KEY, YOUTUBE_DATA_API_KEY]
requirements: [googleapiclient, pytube, youtube_transcript_api]
version: "1.0.0"
---
# YouTube

YouTube tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `youtube.channel` | YouTube Channel | ✅ | Retrieves detailed information and statistics about YouTube channels. |
| `youtube.comments` | YouTube Comments | ✅ | Retrieves and analyzes comments from YouTube videos. |
| `youtube.playlist` | YouTube Playlist | ✅ | Extracts all video URLs from a YouTube playlist. |
| `youtube.search` | YouTube Search | ✅ | Searches YouTube videos based on query. |
| `youtube.transcripts` | YouTube Transcripts | ✅ | Extracts spoken content from YouTube videos with multiple output options. |
| `youtube.trending` | YouTube Trending | ✅ | Retrieves trending videos from YouTube with filtering options. |
| `youtube.video_details` | YouTube Video Details | ✅ | Retrieves detailed information and statistics about YouTube videos. |

All 7 tools are implemented.

## Credentials

`YOUTUBE_API_KEY`, `YOUTUBE_DATA_API_KEY`, an `api_key` argument on the call, or a `youtube_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
