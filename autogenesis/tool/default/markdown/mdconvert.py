import os
from dotenv import load_dotenv
load_dotenv(verbose=True)

from markitdown import MarkItDown
import io
import base64
from typing import BinaryIO, Any
import camelot
import tempfile
import asyncio  
import threading
from markitdown.converters import PdfConverter
from markitdown.converters import AudioConverter
from markitdown.converters._pdf_converter import _dependency_exc_info
from markitdown.converters._exiftool import exiftool_metadata
from markitdown._stream_info import StreamInfo
from markitdown._base_converter import DocumentConverterResult
from markitdown._exceptions import MissingDependencyException, MISSING_DEPENDENCY_MESSAGE
import pdfminer
import pdfminer.high_level


from autogenesis.model import model_manager
from autogenesis.message import HumanMessage, SystemMessage, ContentPartText, ContentPartAudio, AudioURL
from autogenesis.logger import logger


def read_tables_from_stream(file_stream):
    """Extract tables from a PDF byte stream using Camelot.

    Camelot only reads from a path, so the stream is spooled to a temporary
    ".pdf" file and parsed with the "lattice" flavor.

    Args:
        file_stream: A readable binary stream containing PDF bytes.

    Returns:
        A Camelot ``TableList`` of detected tables.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp_pdf:
        temp_pdf.write(file_stream.read())
        temp_pdf.flush()
        tables = camelot.read_pdf(temp_pdf.name, flavor="lattice")
        return tables

def transcribe_audio(file_stream, audio_format):
    """Transcribe audio file using model_manager (synchronous wrapper for async call)."""
    audio_base64 = base64.b64encode(file_stream).decode("utf-8")
    audio_url = "data:audio/" + audio_format + ";base64," + audio_base64
    messages = [
        SystemMessage(content="You are a helpful assistant that transcribes audio files."),
        HumanMessage(content=[
            ContentPartText(text="Please transcribe the audio file and provide the transcription. Only return the transcription, no other text or formatting."),
            ContentPartAudio(audio_url=AudioURL(url=audio_url)),
        ]),
    ]
    
    async def _transcribe_async():
        """Internal async function to call model_manager."""
        response = await model_manager(name="openai/gpt-4o-transcribe", input={"messages": messages})
        return response.message.strip()
    
    # Run async function in sync context
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we get here, there's a running loop - use create_task and wait
        result = None
        exception = None
        
        def run_in_thread():
            """Run the async transcription in a fresh event loop on this thread.

            Used when a loop is already running so ``asyncio.run`` can be called
            safely; stores the outcome in the enclosing ``result``/``exception``.
            """
            nonlocal result, exception
            try:
                result = asyncio.run(_transcribe_async())
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if exception:
            raise exception
        return result
    except RuntimeError:
        # No running event loop, can use asyncio.run directly
        return asyncio.run(_transcribe_async())

class AudioWhisperConverter(AudioConverter):

    def convert(
            self,
            file_stream: BinaryIO,
            stream_info: StreamInfo,
            **kwargs: Any,  # Options to pass to the converter
    ) -> DocumentConverterResult:
        """Convert an audio stream to markdown with metadata and an LLM transcript.

        Overrides MarkItDown's default audio converter to transcribe via
        ``transcribe_audio`` (model-backed) instead of a local ASR engine. Emits any
        available ExifTool metadata followed by an "Audio Transcript" section. WAV,
        MP3, and MP4/M4A are supported; other formats yield metadata only.

        Args:
            file_stream: Binary audio stream.
            stream_info: Detected extension/mimetype used to pick the audio format.
            **kwargs: Passthrough options (e.g. ``exiftool_path``).

        Returns:
            A ``DocumentConverterResult`` holding the assembled markdown.
        """
        md_content = ""

        # Add metadata
        metadata = exiftool_metadata(
            file_stream, exiftool_path=kwargs.get("exiftool_path")
        )
        if metadata:
            for f in [
                "Title",
                "Artist",
                "Author",
                "Band",
                "Album",
                "Genre",
                "Track",
                "DateTimeOriginal",
                "CreateDate",
                # "Duration", -- Wrong values when read from memory
                "NumChannels",
                "SampleRate",
                "AvgBytesPerSec",
                "BitsPerSample",
            ]:
                if f in metadata:
                    md_content += f"{f}: {metadata[f]}\n"

        # Figure out the audio format for transcription
        if stream_info.extension == ".wav" or stream_info.mimetype == "audio/x-wav":
            audio_format = "wav"
        elif stream_info.extension == ".mp3" or stream_info.mimetype == "audio/mpeg":
            audio_format = "mp3"
        elif (
                stream_info.extension in [".mp4", ".m4a"]
                or stream_info.mimetype == "video/mp4"
        ):
            audio_format = "mp4"
        else:
            audio_format = None

        # Transcribe
        if audio_format:
            try:
                transcript = transcribe_audio(file_stream, audio_format=audio_format)
                if transcript:
                    md_content += "\n\n### Audio Transcript:\n" + transcript
            except MissingDependencyException:
                pass

        # Return the result
        return DocumentConverterResult(markdown=md_content.strip())

class PdfWithTableConverter(PdfConverter):
    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> DocumentConverterResult:
        """Convert a PDF to markdown, appending any detected tables.

        Extends MarkItDown's ``PdfConverter`` by combining pdfminer text extraction
        with Camelot table detection: extracted tables are rendered as markdown and
        appended after the body text. Falls back to plain text when no tables are found.

        Args:
            file_stream: Binary PDF stream.
            stream_info: Stream metadata (unused here but part of the converter contract).
            **kwargs: Passthrough converter options.

        Returns:
            A ``DocumentConverterResult`` with the markdown body plus any tables.

        Raises:
            MissingDependencyException: If the PDF dependencies are unavailable.
        """
        # Check the dependencies
        if _dependency_exc_info is not None:
            raise MissingDependencyException(
                MISSING_DEPENDENCY_MESSAGE.format(
                    converter=type(self).__name__,
                    extension=".pdf",
                    feature="pdf",
                )
            ) from _dependency_exc_info[
                1
            ].with_traceback(  # type: ignore[union-attr]
                _dependency_exc_info[2]
            )

        assert isinstance(file_stream, io.IOBase)  # for mypy

        tables = read_tables_from_stream(file_stream)
        num_tables = tables.n
        if num_tables == 0:
            return DocumentConverterResult(
                markdown=pdfminer.high_level.extract_text(file_stream),
            )
        else:
            markdown_content = pdfminer.high_level.extract_text(file_stream)
            table_content = ""
            for i in range(num_tables):
                table = tables[i].df
                table_content += f"Table {i + 1}:\n" + table.to_markdown(index=False) + "\n\n"
            markdown_content += "\n\n" + table_content
            return DocumentConverterResult(
                markdown=markdown_content,
            )

class MarkitdownConverter():
    def __init__(self, timeout: int = 30):

        self.timeout = timeout
        
        self.client = MarkItDown(
            enable_plugins=True,
            llm_model="gpt-4.1",
            llm_prompt="Please describe the content of the image in as much detail as possible."
        )

        removed_converters = [
            PdfConverter, AudioConverter
        ]

        self.client._converters = [
            converter for converter in self.client._converters
            if not isinstance(converter.converter, tuple(removed_converters))
        ]
        self.client.register_converter(PdfWithTableConverter())
        self.client.register_converter(AudioWhisperConverter())

    def convert(self, source: str, **kwargs: Any):
        """Convert a source (path or URL) to markdown via the configured MarkItDown client.

        Args:
            source: File path or URL to convert.
            **kwargs: Options forwarded to ``MarkItDown.convert``.

        Returns:
            The MarkItDown conversion result, or ``None`` if conversion raises (the
            error is logged rather than propagated).
        """
        try:
            result = self.client.convert(
                source,
                **kwargs)
            return result
        except Exception as e:
            logger.error(f"Error during conversion: {e}")
            return None