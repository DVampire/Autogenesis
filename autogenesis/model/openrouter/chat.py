from collections.abc import Iterable, Mapping
from typing import Any, Literal, Optional, Union, List, Dict, Type, overload
import httpx
import json
import dirtyjson

try:
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
    from openai.types.chat import ChatCompletionContentPartTextParam
    from openai.types.chat.chat_completion import ChatCompletion
    from openai.types.shared.chat_model import ChatModel
    from openai.types.shared_params.reasoning_effort import ReasoningEffort
    from openai.types.shared_params.response_format_json_schema import JSONSchema, ResponseFormatJSONSchema
except ImportError:
    # Fallback if openai package is not available
    AsyncOpenAI = None
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception
    ChatCompletion = dict
    ChatModel = str
    ReasoningEffort = str
    JSONSchema = dict
    ResponseFormatJSONSchema = dict
    ChatCompletionContentPartTextParam = dict

from pydantic import BaseModel, Field, ConfigDict

from autogenesis.logger import logger
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage, BaseChatModel
from autogenesis.message.types import Message
from autogenesis.model.openrouter.serializer import OpenRouterChatSerializer
from autogenesis.model.openrouter.rest import OpenRouterClient
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool

class ChatOpenRouter(BaseChatModel):
    """
    A wrapper around AsyncOpenAI that provides a unified interface for OpenRouter chat completions.

    OpenRouter uses OpenAI-compatible API, so we can use AsyncOpenAI client with OpenRouter's base URL.
    Chat/stream orchestration lives in BaseChatModel; this class only supplies the
    OpenRouter wire details (_build_params / _call_model / _open_stream / _parse_stream /
    _format_response). Structured output is native response_format (mode "native").
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    # OpenAI-compatible chat/completions: true streaming + native response_format.
    supports_true_streaming: bool = True

    # Model configuration
    model: Union[ChatModel, str]

    # Model params
    temperature: Optional[float] = 0.7
    frequency_penalty: Optional[float] = 0.3
    reasoning: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    top_p: Optional[float] = None
    max_completion_tokens: Optional[int] = 16384
    
    # OpenRouter plugins (for PDF parsing, etc.)
    plugins: Optional[List[Dict[str, Any]]] = None

    # Client initialization parameters
    api_key: Optional[str] = None
    base_url: Optional[Union[str, httpx.URL]] = "https://openrouter.ai/api/v1"
    timeout: Optional[Union[float, httpx.Timeout]] = httpx.Timeout(1800.0, connect=30.0)
    max_retries: int = 0
    default_headers: Optional[Mapping[str, str]] = None
    default_query: Optional[Mapping[str, object]] = None
    http_client: Optional[httpx.AsyncClient] = None
    _strict_response_validation: bool = False

    # OpenRouter specific headers
    http_referer: Optional[str] = None  # HTTP-Referer header
    x_title: Optional[str] = None  # X-Title header

    reasoning_models: Optional[List[Union[ChatModel, str]]] = Field(
        default_factory=lambda: []
    )

    @property
    def provider(self) -> str:
        return 'openrouter'

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    def _get_client_params(self) -> dict[str, Any]:
        """Prepare client parameters dictionary."""
        # Prepare default headers for OpenRouter
        headers = dict(self.default_headers) if self.default_headers else {}
        
        # Add OpenRouter-specific headers
        if self.http_referer:
            headers['HTTP-Referer'] = self.http_referer
        if self.x_title:
            headers['X-Title'] = self.x_title
        
        base_params = {
            'api_key': self.api_key,
            'base_url': self.base_url,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'default_headers': headers if headers else None,
            'default_query': self.default_query,
            '_strict_response_validation': self._strict_response_validation,
        }

        # Create client_params dict with non-None values
        client_params = {k: v for k, v in base_params.items() if v is not None}

        # Add http_client if provided
        if self.http_client is not None:
            client_params['http_client'] = self.http_client

        return client_params

    def get_openrouter_client(self) -> OpenRouterClient:
        """Get OpenRouterClient for plugins support."""
        return OpenRouterClient(
            api_key=self.api_key,
            base_url=str(self.base_url) if self.base_url else None,
            http_referer=self.http_referer,
            x_title=self.x_title,
            default_headers=self.default_headers,
            timeout=self.timeout,
            http_client=self.http_client,
        )
    
    def get_openai_client(self) -> AsyncOpenAI:
        """Get AsyncOpenAI client for normal requests."""
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")
        
        client_params = self._get_client_params()
        return AsyncOpenAI(**client_params)

    @property
    def name(self) -> str:
        return str(self.model)

    def _get_usage(self, response: ChatCompletion) -> Optional[Dict[str, Any]]:
        """Extract usage information from response."""
        if response.usage is not None:
            usage = response.usage.model_dump()
            return usage
        else:
            return None

    def _get_reasoning(self, message) -> Optional[str]:
        """Extract reasoning information from message."""
        reasoning = None
        try:
            # Try to get reasoning directly from message
            if hasattr(message, 'reasoning') and message.reasoning is not None:
                reasoning = message.reasoning
            elif hasattr(message, 'reasoning_details') and message.reasoning_details is not None:
                # Try to extract from reasoning_details
                reasoning_details = message.reasoning_details
                if reasoning_details:
                    for detail in reasoning_details:
                        if hasattr(detail, 'type'):
                            detail_type = detail.type
                            if detail_type == "reasoning.text" and hasattr(detail, 'text'):
                                reasoning = detail.text
                                break
                            elif detail_type == "reasoning.summary" and hasattr(detail, 'summary'):
                                reasoning = detail.summary
                                break
                        elif isinstance(detail, dict):
                            detail_type = detail.get("type")
                            if detail_type == "reasoning.text":
                                reasoning = detail.get("text")
                                break
                            elif detail_type == "reasoning.summary":
                                reasoning = detail.get("summary")
                                break
        except (AttributeError, KeyError, TypeError, IndexError):
            pass

        return reasoning

    async def _build_params(
        self,
        messages: List[Message],
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[BaseModel, Dict]] = None,
        stream: bool = False,
        plugins: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build parameters for API call.
        
        Step 1: Convert messages, tools, and response_format into API-ready parameters.
        
        Args:
            messages: List of Message objects
            tools: Optional list of Tool instances
            response_format: Optional response format (Pydantic model or dict)
            stream: Whether to stream the response
            plugins: Optional list of plugins
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing:
            - messages: Serialized messages
            - plugins: Plugins to use (if any)
            - params: All other API parameters (tools, response_format, stream, etc.)
        """
        # Serialize messages to OpenRouter format
        openrouter_messages = OpenRouterChatSerializer.serialize_messages(messages)
        
        # Build API parameters
        params: Dict[str, Any] = {}
        
        # Add model parameters
        if self.temperature is not None:
            params['temperature'] = self.temperature
        if self.frequency_penalty is not None:
            params['frequency_penalty'] = self.frequency_penalty
        if self.max_completion_tokens is not None:
            params['max_completion_tokens'] = self.max_completion_tokens
        if self.top_p is not None:
            params['top_p'] = self.top_p
        if self.seed is not None:
            params['seed'] = self.seed
        if self.reasoning is not None:
            params['extra_body'] = self.reasoning
        
        # Handle reasoning models (if any)
        if self.reasoning_models and any(str(m).lower() in str(self.model).lower() for m in self.reasoning_models):
            # Remove temperature and frequency_penalty for reasoning models
            params.pop('temperature', None)
            params.pop('frequency_penalty', None)
        
        # Format tools using serializer
        if tools:
            formatted_tools = OpenRouterChatSerializer.serialize_tools(tools)
            if formatted_tools:
                params['tools'] = formatted_tools
        
        # Handle response_format
        if response_format:
            if isinstance(response_format, type) and issubclass(response_format, BaseModel):
                # Pydantic model class - convert to JSON schema format using serializer
                params['response_format'] = OpenRouterChatSerializer.serialize_response_format(response_format, model_name=self.model)
            elif isinstance(response_format, BaseModel):
                # BaseModel instance - convert to JSON schema format using serializer
                params['response_format'] = OpenRouterChatSerializer.serialize_response_format(response_format, model_name=self.model)
            elif isinstance(response_format, dict):
                # Dict format - use directly
                params['response_format'] = response_format
            else:
                logger.warning(f"Unsupported response_format type: {type(response_format)}")
        
        # Handle streaming
        if stream:
            params['stream'] = True
        
        # Handle plugins
        plugins_to_use = None
        if plugins is not None:
            plugins_to_use = plugins
        elif self.plugins is not None:
            plugins_to_use = self.plugins
        
        # Merge additional kwargs
        params.update(kwargs)
        
        return {
            "messages": openrouter_messages,
            "plugins": plugins_to_use,
            "params": params,
        }

    async def _call_model(self, built: Dict[str, Any]) -> ChatCompletion:
        """Perform one non-streaming API call from a _build_params result.

        Uses OpenRouterClient when plugins are present, else the AsyncOpenAI
        client. Both share client.chat.completions.create().
        """
        messages = built["messages"]
        plugins = built.get("plugins")
        params = built["params"]
        import time as _t
        _start = _t.time()

        try:
            if plugins:
                client = self.get_openrouter_client()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    plugins=plugins,
                    **params,
                )
            else:
                client = self.get_openai_client()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **params,
                )
        except Exception as e:
            _elapsed = _t.time() - _start
            logger.error(f"| 🔴 OpenRouter SDK error ({_elapsed:.0f}s, model={self.model}): {type(e).__name__}: {e}")
            raise

        return response
    
    async def _format_response(
        self,
        response: ChatCompletion,
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[BaseModel, Dict]] = None,
    ) -> Response:
        """Format OpenRouter response into Response."""
        try:
            if not response.choices:
                raw = response.model_dump() if hasattr(response, 'model_dump') else str(response)
                # Surface the real reason: OpenRouter returns HTTP 200 with an
                # `error` field (and empty choices) when the upstream provider
                # fails/rate-limits/filters — this is NOT a schema/strict issue.
                err = raw.get("error") if isinstance(raw, dict) else None
                logger.warning(
                    f"| ⚠️ OpenRouter returned no choices (model={self.model}): "
                    f"error={err!r} raw={raw}"
                )
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message=f"No choices in response (upstream error={err})" if err else "No choices in response",
                    data={"raw_response": raw},
                )

            message = response.choices[0].message
            usage = self._get_usage(response)
            finish_reason = response.choices[0].finish_reason
            reasoning = self._get_reasoning(message)

            # Handle function calling
            if tools and message.tool_calls:
                # Format tool_calls as string
                formatted_lines = []
                functions = []

                for tool_call in message.tool_calls:
                    function_info = tool_call.function
                    name = function_info.name
                    arguments_str = function_info.arguments

                    # Parse arguments if it's a string
                    try:
                        arguments = dirtyjson.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    except (dirtyjson.Error, ValueError, TypeError):
                        arguments = {}

                    # Format arguments as keyword arguments
                    if arguments:
                        args_str = ", ".join([f"{k}={v!r}" for k, v in arguments.items()])
                        formatted_lines.append(f"Calling function {name}({args_str})")
                    else:
                        formatted_lines.append(f"Calling function {name}()")

                    functions.append({
                        "name": name,
                        "arguments": arguments
                    })

                formatted_message = "\n".join(formatted_lines)


                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=formatted_message,
                    data={
                        "raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response),
                        "functions": functions,
                        "usage": usage,
                        "finish_reason": finish_reason,
                        "reasoning": reasoning,
                    },
                    usage=TokenUsage.from_raw(usage),
                )

            # Handle structured output
            elif response_format and isinstance(response_format, type) and issubclass(response_format, BaseModel):
                content = message.content or ""
                if not content:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message="Empty response content from model",
                        data={"raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response)},
                    )

                # Parse JSON content
                try:
                    data = dirtyjson.loads(content)
                    parsed_model = response_format.model_validate(data)

                    # Format as string
                    model_name = response_format.__name__
                    model_dict = parsed_model.model_dump()

                    field_lines = []
                    for field_name, field_value in model_dict.items():
                        field_lines.append(f"{field_name}={field_value!r}")

                    formatted_message = f"Response result:\n\n{model_name}(\n"
                    formatted_message += ",\n".join(f"    {line}" for line in field_lines)
                    formatted_message += "\n)"


                    return Response(
                        type=ResponseType.LLM,
                        success=True,
                        message=formatted_message,
                        data={
                            "raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response),
                            "usage": usage,
                            "finish_reason": finish_reason,
                            "reasoning": reasoning,
                        },
                        usage=TokenUsage.from_raw(usage),
                        parsed_model=parsed_model,
                    )
                except (dirtyjson.Error, ValueError, TypeError) as e:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message=f"Failed to parse JSON from response: {e}",
                        data={"error": str(e), "content": content},
                    )
                except Exception as e:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message=f"Failed to validate response against schema: {e}",
                        data={"error": str(e), "content": content},
                    )

            # Default: return content as string
            else:
                content = message.content or ""


                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=content,
                    data={
                        "raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response),
                        "usage": usage,
                        "finish_reason": finish_reason,
                        "reasoning": reasoning,
                    },
                    usage=TokenUsage.from_raw(usage),
                )

        except Exception as e:
            logger.error(f"Failed to format response: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Failed to format response: {e}",
                data={"error": str(e)},
            )

    async def _open_stream(self, built: Dict[str, Any]):
        """Open OpenRouter's native SSE stream from a _build_params result.

        Uses the AsyncOpenAI-compatible client (OpenRouter's OpenAI endpoint);
        plugins are passed via ``extra_body`` when present.
        """
        params = dict(built["params"])
        params.pop("stream", None)
        params.setdefault("stream_options", {"include_usage": True})
        if built.get("plugins"):
            extra = dict(params.get("extra_body") or {})
            extra["plugins"] = built["plugins"]
            params["extra_body"] = extra
        client = self.get_openai_client()
        return await client.chat.completions.create(
            model=self.model, messages=built["messages"], stream=True, **params
        )

    async def _parse_stream(self, raw):
        """Translate OpenAI-shaped chunks → canonical stream events. Unit-testable."""
        from autogenesis.model.types import (
            TextDelta, ThinkingDelta, ToolCallStart, ToolCallArgsDelta, StreamDone, normalize_stop_reason,
        )
        usage = None
        finish = None
        async for chunk in raw:
            u = getattr(chunk, "usage", None)
            if u is not None:
                usage = u.model_dump() if hasattr(u, "model_dump") else dict(u)
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is not None:
                content = getattr(delta, "content", None)
                if content:
                    yield TextDelta(content)
                rc = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
                if rc:
                    yield ThinkingDelta(rc)
                for tc in (getattr(delta, "tool_calls", None) or []):
                    idx = getattr(tc, "index", 0)
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", None) if fn else None
                    tc_id = getattr(tc, "id", None)
                    if tc_id or name:
                        yield ToolCallStart(index=idx, id=tc_id or "", name=name or "")
                    args = getattr(fn, "arguments", None) if fn else None
                    if args:
                        yield ToolCallArgsDelta(index=idx, partial_json=args)
            fr = getattr(choice, "finish_reason", None)
            if fr:
                finish = fr
        yield StreamDone(stop_reason=normalize_stop_reason(finish), usage=usage)
