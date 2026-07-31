from collections.abc import Iterable, Mapping
from typing import Any, Literal, Optional, Union, BinaryIO, List, Dict
import httpx
import os
import aiohttp
import base64

try:
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
    from openai.types.shared.chat_model import ChatModel
except ImportError:
    # Fallback if openai package is not available
    AsyncOpenAI = None
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception
    ChatModel = str

from pydantic import BaseModel, Field, ConfigDict

from autogenesis.message.types import Message, HumanMessage, ContentPartAudio
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage
from autogenesis.logger import logger
from autogenesis.utils import assemble_workspace_path


class TranscribeOpenAI(BaseModel):
    """
    A wrapper around AsyncOpenAI that provides a unified interface for OpenAI audio transcriptions.
    
    This class is specifically designed for audio transcription models like gpt-4o-transcribe.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    # Model configuration
    model: Union[ChatModel, str] = "gpt-4o-transcribe"

    # Client initialization parameters
    api_key: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    base_url: Optional[Union[str, httpx.URL]] = None
    websocket_base_url: Optional[Union[str, httpx.URL]] = None
    timeout: Optional[Union[float, httpx.Timeout]] = None
    max_retries: int = 5
    default_headers: Optional[Mapping[str, str]] = None
    default_query: Optional[Mapping[str, object]] = None
    http_client: Optional[httpx.AsyncClient] = None
    _strict_response_validation: bool = False

    # Transcription parameters
    language: Optional[str] = None
    prompt: Optional[str] = None
    response_format: Optional[str] = None  # "json", "text", "srt", "verbose_json", "vtt"
    temperature: Optional[float] = None
    timestamp_granularities: Optional[list[str]] = None  # ["word", "segment"]

    @property
    def provider(self) -> str:
        return 'openai'

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    def _get_client_params(self) -> dict[str, Any]:
        """Prepare client parameters dictionary."""
        base_params = {
            'api_key': self.api_key,
            'organization': self.organization,
            'project': self.project,
            'base_url': self.base_url,
            'websocket_base_url': self.websocket_base_url,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'default_headers': self.default_headers,
            'default_query': self.default_query,
            '_strict_response_validation': self._strict_response_validation,
        }

        # Create client_params dict with non-None values
        client_params = {k: v for k, v in base_params.items() if v is not None}

        # Add http_client if provided
        if self.http_client is not None:
            client_params['http_client'] = self.http_client

        return client_params

    def get_client(self) -> AsyncOpenAI:
        """
        Returns an AsyncOpenAI client.

        Returns:
            AsyncOpenAI: An instance of the AsyncOpenAI client.
        """
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")
        
        client_params = self._get_client_params()
        return AsyncOpenAI(**client_params)

    @property
    def name(self) -> str:
        return str(self.model)

    def _extract_audio_from_messages(self, messages: List[Message]) -> tuple[Optional[Union[str, BinaryIO]], Optional[str], Optional[str]]:
        """Extract audio file, prompt text, and filename from messages.
        
        Returns:
            Tuple of (audio_file, prompt_text, filename)
        """
        audio_file = None
        prompt_text = None
        filename = None
        
        for message in messages:
            if isinstance(message, HumanMessage):
                if isinstance(message.content, list):
                    for part in message.content:
                        if isinstance(part, ContentPartAudio):
                            audio_url = part.audio_url.url
                            # Handle data URLs (base64 encoded)
                            if audio_url.startswith("data:"):
                                # Base64 encoded audio - decode it
                                # Format: data:audio/mp3;base64,<base64_data> or data:audio/mpeg;base64,<base64_data>
                                try:
                                    if "," in audio_url:
                                        header, data = audio_url.split(",", 1)
                                        audio_bytes = base64.b64decode(data)
                                        # Create a temporary file-like object
                                        from io import BytesIO
                                        audio_file = BytesIO(audio_bytes)
                                        
                                        # Extract filename from mime type
                                        if "audio/mpeg" in header or "audio/mp3" in header:
                                            filename = "audio.mp3"
                                        elif "audio/wav" in header:
                                            filename = "audio.wav"
                                        elif "audio/ogg" in header:
                                            filename = "audio.ogg"
                                        elif "audio/flac" in header:
                                            filename = "audio.flac"
                                        elif "audio/m4a" in header:
                                            filename = "audio.m4a"
                                        else:
                                            filename = "audio.mp3"  # Default
                                    else:
                                        logger.error(f"Invalid data URL format: {audio_url}")
                                        return None, None, None
                                except Exception as e:
                                    logger.error(f"Failed to decode base64 audio: {e}")
                                    return None, None, None
                            # Handle file:// URLs
                            elif audio_url.startswith("file://"):
                                # Remove file:// prefix
                                file_path = audio_url[7:]
                                # Handle absolute paths
                                if not os.path.isabs(file_path):
                                    file_path = assemble_workspace_path(file_path)
                                audio_file = file_path
                                filename = os.path.basename(file_path)
                            elif os.path.exists(audio_url):
                                # Direct file path
                                audio_file = audio_url
                                filename = os.path.basename(audio_url)
                            elif os.path.exists(assemble_workspace_path(audio_url)):
                                # Relative file path
                                audio_file = assemble_workspace_path(audio_url)
                                filename = os.path.basename(audio_file)
                            else:
                                # Try to download from URL (http/https)
                                logger.info(f"Audio URL detected, will download: {audio_url}")
                                audio_file = audio_url
                                # Extract filename from URL if possible
                                filename = os.path.basename(audio_url.split("?")[0]) or "audio.mp3"
                        elif hasattr(part, 'type') and part.type == 'text':
                            # Collect text as prompt
                            if prompt_text is None:
                                prompt_text = part.text
                            else:
                                prompt_text += " " + part.text
                elif isinstance(message.content, str):
                    # Text-only message, use as prompt
                    if prompt_text is None:
                        prompt_text = message.content
                    else:
                        prompt_text += " " + message.content
        
        return audio_file, prompt_text, filename

    def _cleanup_file_resources(self, file_obj: Any, temp_file_path: Optional[str] = None) -> None:
        """Clean up file resources (close file handles and delete temporary files)."""
        # Close file if we opened it (but not if it's BytesIO from base64 or tuple)
        if file_obj is not None:
            # Handle tuple format: (filename, file_obj)
            actual_file = file_obj[1] if isinstance(file_obj, tuple) else file_obj
            
            if hasattr(actual_file, 'close'):
                # Only close if it's not a BytesIO (which might be reused)
                from io import BytesIO
                if not isinstance(actual_file, BytesIO):
                    try:
                        actual_file.close()
                    except Exception as e:
                        logger.debug(f"Error closing file: {e}")
        
        # Clean up temporary file if we downloaded it
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")

    async def _download_audio_file(self, url: str) -> Optional[str]:
        """Download audio file from URL to temporary file."""
        try:
            import tempfile
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # Create temporary file
                        ext = os.path.splitext(url)[1] or '.mp3'
                        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                            async for chunk in response.content.iter_chunked(8192):
                                tmp_file.write(chunk)
                            return tmp_file.name
                    else:
                        logger.error(f"Failed to download audio: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading audio file: {e}")
            return None

    async def _build_params(
        self,
        messages: List[Message],
        language: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
        timestamp_granularities: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build parameters for API call.
        
        Step 1: Extract audio file and build API parameters.
        
        Args:
            messages: List of Message objects (will extract audio file and prompt text from messages)
            language: Optional language code (e.g., "en", "zh")
            response_format: Optional response format ("json", "text", "srt", "verbose_json", "vtt")
            temperature: Optional temperature parameter
            timestamp_granularities: Optional list of timestamp granularities (["word", "segment"])
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing:
            - file: Audio file object
            - params: All other API parameters
            - temp_file_path: Temporary file path (if downloaded) for cleanup
        """
        # Extract audio file, prompt, and filename from messages
        audio_file, extracted_prompt, extracted_filename = self._extract_audio_from_messages(messages)
        if audio_file is None:
            raise ValueError("No audio file found in messages")
        
        # Use extracted prompt from messages
        prompt = extracted_prompt
        filename = extracted_filename or "audio.mp3"  # Default filename

        # Handle file input - convert to file object
        file_obj = None
        temp_file_path = None
        
        # Check if it's a file-like object (BytesIO or other BinaryIO)
        from io import BytesIO
        if isinstance(audio_file, BytesIO) or (hasattr(audio_file, 'read') and hasattr(audio_file, 'seek')):
            # Already a file-like object (BytesIO from base64)
            # Reset position to beginning (important!)
            audio_file.seek(0)
            # OpenAI SDK accepts file objects directly, but may need filename for format detection
            # Use tuple format: (filename, file_obj)
            file_obj = (filename, audio_file)
        elif isinstance(audio_file, str):
            # String - could be URL or file path
            if audio_file.startswith(("http://", "https://")):
                # Download the file
                temp_file_path = await self._download_audio_file(audio_file)
                if temp_file_path is None:
                    raise ValueError(f"Failed to download audio file from URL: {audio_file}")
                file_obj = open(temp_file_path, "rb")
            elif audio_file.startswith("file://"):
                # Remove file:// prefix
                file_path = audio_file[7:]
                if not os.path.isabs(file_path):
                    file_path = assemble_workspace_path(file_path)
                if not os.path.exists(file_path):
                    raise ValueError(f"Audio file not found: {file_path}")
                file_obj = open(file_path, "rb")
            else:
                # Regular file path
                if not os.path.exists(audio_file):
                    # Try relative path
                    file_path = assemble_workspace_path(audio_file)
                    if not os.path.exists(file_path):
                        raise ValueError(f"Audio file not found: {audio_file}")
                    audio_file = file_path
                file_obj = open(audio_file, "rb")
        else:
            raise ValueError(f"Unsupported audio file type: {type(audio_file)}")

        # Build API parameters
        params: Dict[str, Any] = {
            "model": self.model,
            "file": file_obj,
        }

        # Add transcription parameters
        if language is not None:
            params["language"] = language
        elif self.language is not None:
            params["language"] = self.language

        # Add prompt from messages if available
        if prompt:
            params["prompt"] = prompt
        elif self.prompt is not None:
            params["prompt"] = self.prompt

        if response_format is not None:
            params["response_format"] = response_format
        elif self.response_format is not None:
            params["response_format"] = self.response_format

        if temperature is not None:
            params["temperature"] = temperature
        elif self.temperature is not None:
            params["temperature"] = self.temperature

        if timestamp_granularities is not None:
            params["timestamp_granularities"] = timestamp_granularities
        elif self.timestamp_granularities is not None:
            params["timestamp_granularities"] = self.timestamp_granularities

        # Merge additional kwargs
        params.update(kwargs)

        return {
            "file": file_obj,
            "params": params,
            "temp_file_path": temp_file_path,
        }

    async def _call_model(
        self,
        file_obj: Any,
        **params: Any,
    ) -> Any:
        """
        Call the model API (Step 2).
        
        Unified interface for calling the transcription API.
        
        Args:
            file_obj: Audio file object
            **params: API parameters
            
        Returns:
            Transcription response object
        """
        client = self.get_client()
        response = await client.audio.transcriptions.create(**params)
        
        return response

    async def _format_response(
        self,
        transcription: Any,
        temp_file_path: Optional[str] = None,
        file_obj: Optional[Any] = None,
    ) -> Response:
        """
        Format transcription response into Response (Step 3).
        
        Args:
            transcription: Transcription response object
            temp_file_path: Temporary file path (if downloaded) for cleanup
            file_obj: File object for cleanup
            
        Returns:
            Response with transcribed text
        """
        # Extract text from transcription response
        text = ""
        if hasattr(transcription, 'text'):
            text = transcription.text
        elif isinstance(transcription, dict):
            text = transcription.get('text', '')
        elif isinstance(transcription, str):
            text = transcription

        # Clean up resources
        self._cleanup_file_resources(file_obj, temp_file_path)

        # Format response
        extra = {
            "raw_response": transcription.model_dump() if hasattr(transcription, 'model_dump') else str(transcription),
        }

        # Add additional fields if available (for verbose_json format)
        if hasattr(transcription, 'words'):
            extra["words"] = transcription.words
        if hasattr(transcription, 'segments'):
            extra["segments"] = transcription.segments

        return Response(
            type=ResponseType.LLM,
            success=True,
            message=text,
            extra=extra
        )

    async def __call__(
        self,
        messages: List[Message],
        language: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
        timestamp_granularities: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Response:
        """
        Execute asynchronous transcription call via OpenAI API.

        Args:
            messages: List of Message objects (will extract audio file and prompt text from messages)
            language: Optional language code (e.g., "en", "zh")
            response_format: Optional response format ("json", "text", "srt", "verbose_json", "vtt")
            temperature: Optional temperature parameter
            timestamp_granularities: Optional list of timestamp granularities (["word", "segment"])
            **kwargs: Additional parameters

        Returns:
            Response with transcribed text
        """
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")

        file_obj = None
        temp_file_path = None
        
        try:
            params = await self._build_params(
                messages=messages,
                language=language,
                response_format=response_format,
                temperature=temperature,
                timestamp_granularities=timestamp_granularities,
                **kwargs,
            )
            
            file_obj = params["file"]
            temp_file_path = params.get("temp_file_path")
            
            transcription = await self._call_model(
                file_obj=file_obj,
                **params["params"],
            )
            
            return await self._format_response(
                transcription=transcription,
                temp_file_path=temp_file_path,
                file_obj=file_obj,
            )

        except RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            self._cleanup_file_resources(file_obj, temp_file_path)
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Rate limit error: {e.message}",
                extra={"error": str(e), "model": self.name}
            )
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            self._cleanup_file_resources(file_obj, temp_file_path)
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API connection error: {str(e)}",
                extra={"error": str(e), "model": self.name}
            )
        except APIStatusError as e:
            logger.error(f"API status error: {e}")
            self._cleanup_file_resources(file_obj, temp_file_path)
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API status error: {e.message}",
                extra={"error": str(e), "status_code": e.status_code, "model": self.name}
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            # Clean up resources on error
            self._cleanup_file_resources(file_obj, temp_file_path)
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Unexpected error: {str(e)}",
                extra={"error": str(e), "model": self.name}
            )
