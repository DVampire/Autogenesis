"""AssemblyAI Start Transcript."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.assemblyai._base import AssemblyaiToolBase


class AssemblyaiStartTranscriptTool(AssemblyaiToolBase):
    """AssemblyAI Start Transcript."""

    name: str = 'assemblyai_start_transcript'
    display_name: str = 'AssemblyAI Start Transcript'
    description: str = 'Create a transcription job for an audio file using AssemblyAI with advanced options'

    async def __call__(self, audio_url: str = "", speech_model: str = "best", api_key: str = "", **kwargs) -> Response:
        try:
            aai = self._aai(api_key)
            if not str(audio_url or "").strip():
                return self._fail("assemblyai.start_transcript: 'audio_url' is required.")
            config = aai.TranscriptionConfig(speech_model=speech_model)
            transcript = aai.Transcriber().submit(audio_url, config=config)
            return self._ok(f"Submitted transcription {transcript.id} ({transcript.status}).",
                            transcript_id=transcript.id, status=str(transcript.status))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"assemblyai.assemblyai_start_transcript: {type(exc).__name__}: {exc}")
