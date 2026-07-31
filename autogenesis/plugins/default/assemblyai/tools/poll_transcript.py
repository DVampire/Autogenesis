"""AssemblyAI Poll Transcript."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.assemblyai._base import AssemblyaiToolBase


class AssemblyaiPollTranscriptTool(AssemblyaiToolBase):
    """AssemblyAI Poll Transcript."""

    name: str = 'assemblyai_poll_transcript'
    display_name: str = 'AssemblyAI Poll Transcript'
    description: str = 'Poll for the status of a transcription job using AssemblyAI'

    async def __call__(self, transcript_id: str = "", api_key: str = "", **kwargs) -> Response:
        try:
            aai = self._aai(api_key)
            if not transcript_id:
                return self._fail("assemblyai.poll_transcript: 'transcript_id' is required.")
            t = aai.Transcript.get_by_id(transcript_id)
            return self._ok(f"Transcript {transcript_id}: {t.status}.",
                            transcript_id=transcript_id, status=str(t.status), text=t.text)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"assemblyai.assemblyai_poll_transcript: {type(exc).__name__}: {exc}")
