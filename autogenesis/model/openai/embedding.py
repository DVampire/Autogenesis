from collections.abc import Mapping
from typing import Any, Optional, Union, List, Dict
import httpx

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

from pydantic import BaseModel, ConfigDict

from autogenesis.message.types import Message, HumanMessage, SystemMessage, ContentPartText
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage
from autogenesis.logger import logger


class EmbeddingOpenAI(BaseModel):
    """
    A wrapper around AsyncOpenAI that provides a unified interface for OpenAI embeddings.
    
    This class is specifically designed for embedding models like text-embedding-3-small, text-embedding-3-large, etc.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    # Model configuration
    model: Union[ChatModel, str] = "text-embedding-3-small"

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

    # Embedding parameters
    dimensions: Optional[int] = None  # Optional dimensions for text-embedding-3 models
    encoding_format: Optional[str] = None  # "float" or "base64"

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

    def _extract_text_from_messages(self, messages: List[Message]) -> List[str]:
        """Extract text content from messages.
        
        Returns:
            List of text strings extracted from messages
        """
        texts = []
        
        for message in messages:
            if isinstance(message, (HumanMessage, SystemMessage)):
                if isinstance(message.content, str):
                    texts.append(message.content)
                elif isinstance(message.content, list):
                    for part in message.content:
                        if isinstance(part, ContentPartText):
                            texts.append(part.text)
        
        return texts

    async def _build_params(
        self,
        messages: List[Message],
        dimensions: Optional[int] = None,
        encoding_format: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build parameters for API call.
        
        Step 1: Extract text from messages and build API parameters.
        
        Args:
            messages: List of Message objects (will extract text content from messages)
            dimensions: Optional dimensions for text-embedding-3 models
            encoding_format: Optional encoding format ("float" or "base64")
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing:
            - input: Text input (single string or list of strings)
            - params: All other API parameters
        """
        # Extract text from messages
        texts = self._extract_text_from_messages(messages)
        if not texts:
            raise ValueError("No text content found in messages")
        
        # Build API parameters
        params: Dict[str, Any] = {
            "model": self.model,
            "input": texts if len(texts) > 1 else texts[0],  # Single string or list of strings
        }

        # Add embedding parameters
        if dimensions is not None:
            params["dimensions"] = dimensions
        elif self.dimensions is not None:
            params["dimensions"] = self.dimensions

        if encoding_format is not None:
            params["encoding_format"] = encoding_format
        elif self.encoding_format is not None:
            params["encoding_format"] = self.encoding_format

        # Merge additional kwargs
        params.update(kwargs)

        return {
            "input": texts if len(texts) > 1 else texts[0],
            "params": params,
        }

    async def _call_model(
        self,
        input_text: Union[str, List[str]],
        **params: Any,
    ) -> Any:
        """
        Call the model API (Step 2).
        
        Unified interface for calling the embedding API.
        
        Args:
            input_text: Text input (single string or list of strings)
            **params: API parameters (should include 'input' key)
            
        Returns:
            Embedding response object
        """
        client = self.get_client()
        # Ensure 'input' is in params (it should be from _build_params)
        if 'input' not in params:
            params['input'] = input_text
        response = await client.embeddings.create(**params)
        
        return response

    async def _format_response(
        self,
        response: Any,
    ) -> Response:
        """
        Format embedding response into Response (Step 3).
        
        Args:
            response: Embedding response object
            
        Returns:
            Response with embedding vectors
        """
        # Extract embeddings from response
        embeddings = []
        if hasattr(response, 'data'):
            for item in response.data:
                if hasattr(item, 'embedding'):
                    embeddings.append(item.embedding)
                elif isinstance(item, dict):
                    embeddings.append(item.get('embedding'))
        elif isinstance(response, dict):
            data = response.get('data', [])
            for item in data:
                if isinstance(item, dict):
                    embeddings.append(item.get('embedding'))

        # Format response message
        if len(embeddings) == 1:
            message = f"Embedding vector with {len(embeddings[0])} dimensions"
        else:
            message = f"{len(embeddings)} embedding vectors"

        # Format response
        extra = {
            "raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response),
            "embeddings": embeddings,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if hasattr(response, 'usage') and hasattr(response.usage, 'prompt_tokens') else None,
                "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') and hasattr(response.usage, 'total_tokens') else None,
            } if hasattr(response, 'usage') else None,
        }

        return Response(
            type=ResponseType.LLM,
            success=True,
            message=message,
            extra=extra
        )

    async def __call__(
        self,
        messages: List[Message],
        dimensions: Optional[int] = None,
        encoding_format: Optional[str] = None,
        **kwargs: Any,
    ) -> Response:
        """
        Execute asynchronous embedding call via OpenAI API.

        Args:
            messages: List of Message objects (will extract text content from messages)
            dimensions: Optional dimensions for text-embedding-3 models
            encoding_format: Optional encoding format ("float" or "base64")
            **kwargs: Additional parameters

        Returns:
            Response with embedding vectors
        """
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")

        try:
            params = await self._build_params(
                messages=messages,
                dimensions=dimensions,
                encoding_format=encoding_format,
                **kwargs,
            )
            
            response = await self._call_model(
                input_text=params["input"],
                **params["params"],
            )
            
            return await self._format_response(
                response=response,
            )

        except RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Rate limit error: {e.message}",
                extra={"error": str(e), "model": self.name}
            )
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API connection error: {str(e)}",
                extra={"error": str(e), "model": self.name}
            )
        except APIStatusError as e:
            logger.error(f"API status error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API status error: {e.message}",
                extra={"error": str(e), "status_code": e.status_code, "model": self.name}
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Unexpected error: {str(e)}",
                extra={"error": str(e), "model": self.name}
            )

