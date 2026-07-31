import httpx
import json
from typing import Optional, Dict, Any, List, Union
from collections.abc import Mapping

try:
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
    from openai.types.chat.chat_completion_message_function_tool_call_param import Function as ChatCompletionFunction
    from openai.types.completion_usage import CompletionUsage
except ImportError:
    # Fallback if openai package is not available
    ChatCompletion = dict
    Choice = dict
    ChatCompletionMessage = dict
    ChatCompletionMessageToolCall = dict
    ChatCompletionFunction = dict
    CompletionUsage = dict

from autogenesis.logger import logger


class OpenRouterCompletions:
    """OpenRouter completions API client (similar to OpenAI's chat.completions)."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://openrouter.ai/api/v1",
        http_referer: Optional[str] = None,
        x_title: Optional[str] = None,
        default_headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[Union[float, httpx.Timeout]] = 300.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else "https://openrouter.ai/api/v1"
        self.http_referer = http_referer
        self.x_title = x_title
        self.default_headers = default_headers
        self.timeout = timeout
        self._http_client = http_client
        self._endpoint = "/chat/completions"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for the OpenRouter API request."""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # OpenRouter-specific headers
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            headers["X-Title"] = self.x_title
        
        # Merge with default headers if any
        if self.default_headers:
            headers.update(self.default_headers)
        
        return headers
    
    def _get_api_url(self) -> str:
        """Get the API URL for OpenRouter."""
        return f"{self.base_url}{self._endpoint}"
    
    def _dict_to_chat_completion(self, data: Dict[str, Any]) -> ChatCompletion:
        """Convert dict response to ChatCompletion object (compatible with OpenAI SDK)."""
        if ChatCompletion == dict:
            # If OpenAI SDK is not available, return dict as-is
            return data
        
        # Extract choices
        choices_data = data.get("choices", [])
        choices = []
        for choice_data in choices_data:
            message_data = choice_data.get("message", {})
            
            # Build tool_calls if present
            tool_calls = None
            if message_data.get("tool_calls"):
                tool_calls = []
                for tc_data in message_data["tool_calls"]:
                    function_data = tc_data.get("function", {})
                    tool_call = ChatCompletionMessageToolCall(
                        id=tc_data.get("id", ""),
                        type="function",
                        function=ChatCompletionFunction(
                            name=function_data.get("name", ""),
                            arguments=function_data.get("arguments", "{}")
                        )
                    )
                    tool_calls.append(tool_call)
            
            # Build message
            message = ChatCompletionMessage(
                role=message_data.get("role", "assistant"),
                content=message_data.get("content"),
                tool_calls=tool_calls,
            )
            
            # Build choice — normalize finish_reason to values accepted by openai SDK
            # OpenRouter may return non-standard values like "end_turn", "max_tokens", etc.
            _VALID_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter", "function_call"}
            raw_finish = choice_data.get("finish_reason") or "stop"
            finish_reason = raw_finish if raw_finish in _VALID_FINISH_REASONS else "stop"
            choice = Choice(
                finish_reason=finish_reason,
                index=choice_data.get("index", 0),
                message=message,
            )
            choices.append(choice)
        
        # Build usage
        usage_data = data.get("usage", {})
        usage = None
        if usage_data:
            usage = CompletionUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
        
        # Build ChatCompletion
        return ChatCompletion(
            id=data.get("id", ""),
            choices=choices,
            created=data.get("created", 0),
            model=data.get("model", ""),
            object="chat.completion",
            usage=usage,
        )

    async def create(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        plugins: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """
        Create a chat completion (similar to OpenAI's chat.completions.create).
        
        Args:
            model: Model identifier (e.g., "google/gemini-2.5-flash")
            messages: List of message dictionaries
            plugins: Optional list of plugins (e.g., for PDF parsing)
            **kwargs: Additional parameters (temperature, max_completion_tokens, tools, etc.)
        
        Returns:
            ChatCompletion object (compatible with OpenAI SDK format)
        """
        # Build request payload
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        
        # Add plugins if provided
        if plugins is not None:
            payload["plugins"] = plugins
            
        # Add usage parameters
        payload["usage"] = {
            "include": True
        }
        
        # Add other parameters from kwargs
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "max_completion_tokens":  # OpenRouter uses max_tokens instead of max_completion_tokens
                payload["max_tokens"] = value
            else:
                payload[key] = value
        
        # Get headers and URL
        headers = self._get_headers()
        api_url = self._get_api_url()
        
        # Handle timeout
        timeout_obj = self.timeout
        if isinstance(timeout_obj, (int, float)):
            timeout_obj = httpx.Timeout(timeout_obj)
        
        # Make the async request
        try:
            # Use provided http_client or create a new one
            if self._http_client:
                client = self._http_client
                should_close = False
            else:
                client = httpx.AsyncClient(timeout=timeout_obj)
                should_close = True
            
            try:
                response = await client.post(
                    url=api_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_dict = response.json()
                
                # Convert dict to ChatCompletion object
                return self._dict_to_chat_completion(response_dict)
            finally:
                if should_close:
                    await client.aclose()
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API HTTP error: {e}")
            try:
                error_detail = e.response.json()
                raise Exception(f"OpenRouter API request failed: {error_detail}")
            except:
                raise Exception(f"OpenRouter API request failed: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"OpenRouter API request error: {e}")
            raise Exception(f"OpenRouter API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in OpenRouter API request: {e}")
            raise

class OpenRouterChatNamespace:
    """Chat namespace for OpenRouterClient (similar to OpenAI's chat namespace)."""
    
    def __init__(self, completions: OpenRouterCompletions):
        self.completions = completions


class OpenRouterClient:
    """OpenRouter API client (similar to AsyncOpenAI)."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://openrouter.ai/api/v1",
        http_referer: Optional[str] = None,
        x_title: Optional[str] = None,
        default_headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[Union[float, httpx.Timeout]] = 300.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.http_referer = http_referer
        self.x_title = x_title
        self.default_headers = default_headers
        self.timeout = timeout
        self._http_client = http_client
        
        # Initialize completions client
        completions = OpenRouterCompletions(
            api_key=api_key,
            base_url=base_url,
            http_referer=http_referer,
            x_title=x_title,
            default_headers=default_headers,
            timeout=timeout,
            http_client=http_client
        )
        
        # Create chat namespace for compatibility with OpenAI SDK (client.chat.completions.create)
        self.chat = OpenRouterChatNamespace(completions=completions)

