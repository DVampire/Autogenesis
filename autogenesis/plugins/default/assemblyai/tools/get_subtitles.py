"""AssemblyAI Get Subtitles."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.assemblyai._base import AssemblyaiToolBase


class AssemblyaiGetSubtitlesTool(AssemblyaiToolBase):
    """AssemblyAI Get Subtitles."""

    name: str = 'assemblyai_get_subtitles'
    display_name: str = 'AssemblyAI Get Subtitles'
    description: str = 'Export your transcript in SRT or VTT format for subtitles and closed captions'

    async def __call__(self, transcript_id: str = "", subtitle_format: str = "srt", chars_per_caption: int = 0, api_key: str = "", **kwargs) -> Response:
        try:
            aai = self._aai(api_key)
            if not transcript_id:
                return self._fail("assemblyai.get_subtitles: 'transcript_id' is required.")
            t = aai.Transcript.get_by_id(transcript_id)
            cpc = chars_per_caption if chars_per_caption > 0 else None
            subs = t.export_subtitles_srt(cpc) if subtitle_format == "srt" else t.export_subtitles_vtt(cpc)
            return self._ok(f"Exported {subtitle_format} subtitles for {transcript_id}.",
                            subtitles=subs, format=subtitle_format)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"assemblyai.assemblyai_get_subtitles: {type(exc).__name__}: {exc}")
