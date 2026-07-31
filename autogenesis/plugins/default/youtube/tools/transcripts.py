"""YouTube Transcripts — extract spoken content, chunked (ported from Langflow)."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.youtube._base import YoutubeToolBase


class YoutubeTranscriptsTool(YoutubeToolBase):
    """YouTube Transcripts."""

    name: str = 'transcripts'
    display_name: str = 'YouTube Transcripts'
    description: str = 'Extracts spoken content from YouTube videos with multiple output options.'

    async def __call__(self, url: str = "", chunk_size_seconds: int = 60,
                       translation: str = "", **kwargs) -> Response:
        url = str(url or "").strip()
        if not url:
            return self._fail("youtube.transcripts: 'url' is required.")
        try:
            video_id = self._video_id(url)
        except ValueError as exc:
            return self._fail(f"youtube.transcripts: {exc}")
        try:
            from youtube_transcript_api import (  # noqa: PLC0415
                NoTranscriptFound, YouTubeTranscriptApi,
            )

            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            if translation:
                transcript = transcript_list.find_transcript(["en"]).translate(translation)
            else:
                try:
                    transcript = transcript_list.find_transcript(["en"])
                except NoTranscriptFound:
                    transcript = transcript_list.find_generated_transcript(["en"])
            segments = api.fetch(transcript.video_id, [transcript.language_code])
        except Exception as exc:  # noqa: BLE001 — captions may be disabled/blocked
            return self._fail(
                f"youtube.transcripts: could not retrieve transcript for '{video_id}' "
                f"({type(exc).__name__}: {exc}). Captions may be disabled or the video restricted.")

        def _get(seg, attr):
            return getattr(seg, attr) if hasattr(seg, attr) else seg[attr]

        # Chunk into time windows (verbatim from Langflow's _chunk_transcript).
        chunks, current, chunk_start = [], [], 0
        for seg in segments:
            start = _get(seg, "start")
            if start - chunk_start >= chunk_size_seconds and current:
                chunks.append({"start": chunk_start, "text": " ".join(_get(s, "text") for s in current)})
                current, chunk_start = [], start
            current.append(seg)
        if current:
            chunks.append({"start": chunk_start, "text": " ".join(_get(s, "text") for s in current)})

        records = []
        for c in chunks:
            secs = int(c["start"])
            records.append({"timestamp": f"{secs // 60:02d}:{secs % 60:02d}", "text": c["text"]})
        full_text = " ".join(_get(s, "text") for s in segments)
        return self._ok(f"Extracted {len(records)} transcript chunks for '{video_id}'.",
                        video_id=video_id, video_url=url, transcript=full_text,
                        records=records, count=len(records))
