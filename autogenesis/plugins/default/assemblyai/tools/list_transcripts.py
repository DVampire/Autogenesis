"""AssemblyAI List Transcripts."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.assemblyai._base import AssemblyaiToolBase


class AssemblyaiListTranscriptsTool(AssemblyaiToolBase):
    """AssemblyAI List Transcripts."""

    name: str = 'assemblyai_list_transcripts'
    display_name: str = 'AssemblyAI List Transcripts'
    description: str = 'Retrieve a list of transcripts from AssemblyAI with filtering options'

    async def __call__(self, limit: int = 20, api_key: str = "", **kwargs) -> Response:
        try:
            aai = self._aai(api_key)
            params = aai.ListTranscriptParameters()
            params.limit = int(limit)
            page = aai.Transcriber().list_transcripts(params)
            records = [t.dict() if hasattr(t, "dict") else dict(t) for t in page.transcripts]
            return self._ok(f"Listed {len(records)} transcripts.", records=records, count=len(records))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"assemblyai.assemblyai_list_transcripts: {type(exc).__name__}: {exc}")
