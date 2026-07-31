from collections.abc import Mapping
from typing import Any, Literal, Optional, Union, List, Dict, Type
import httpx

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

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.message.types import Message
from autogenesis.model.openai.serializer import OpenAIChatSerializer
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage, BaseChatModel
from autogenesis.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool


class ChatOpenAI(BaseChatModel):
    """
    A wrapper around AsyncOpenAI that provides a unified interface for OpenAI chat completions.

    Chat/stream orchestration lives in BaseChatModel; this class supplies the OpenAI
    wire details. Structured output is native response_format (mode "native").
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    supports_true_streaming: bool = True

    # Model configuration
    model: Union[ChatModel, str]

    # Model params
    temperature: Optional[float] = 0.7
    frequency_penalty: Optional[float] = 0.3
    reasoning: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    service_tier: Optional[Literal['auto', 'default', 'flex', 'priority', 'scale']] = None
    top_p: Optional[float] = None
    max_completion_tokens: Optional[int] = 16384
    plugins: Optional[List[Dict[str, Any]]] = None
    
    # Client initialization parameters
    api_key: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    base_url: Optional[Union[str, httpx.URL]] = None
    websocket_base_url: Optional[Union[str, httpx.URL]] = None
    timeout: Optional[Union[float, httpx.Timeout]] = httpx.Timeout(600.0, connect=30.0)
    max_retries: int = 5
    default_headers: Optional[Mapping[str, str]] = None
    default_query: Optional[Mapping[str, object]] = None
    http_client: Optional[httpx.AsyncClient] = None
    _strict_response_validation: bool = False

    reasoning_models: Optional[List[Union[ChatModel, str]]] = Field(
        default_factory=lambda: [
            'o3',
            'gpt-5',
            'gpt-5.1',
        ]
    )

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
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build parameters for API call.
        
        Step 1: Convert messages, tools, and response_format into API-ready parameters.
        
        Args:
            messages: List of Message objects
            tools: Optional list of Tool instances
            response_format: Optional response format (Pydantic model class, instance or dict)
            stream: Whether to stream the response
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing:
            - messages: Serialized messages
            - params: All other API parameters (tools, response_format, stream, etc.)
        """
        # Serialize messages to OpenAI format
        openai_messages = OpenAIChatSerializer.serialize_messages(messages)
        
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
        if self.service_tier is not None:
            params['service_tier'] = self.service_tier
        if self.reasoning is not None:
            params.update(self.reasoning)
        
        # Handle reasoning models
        if self.reasoning_models and any(str(m).lower() in str(self.model).lower() for m in self.reasoning_models):
            # Remove temperature and frequency_penalty for reasoning models
            params.pop('temperature', None)
            params.pop('frequency_penalty', None)
        
        # Format tools using serializer
        if tools:
            formatted_tools = OpenAIChatSerializer.serialize_tools(tools)
            if formatted_tools:
                params['tools'] = formatted_tools
        
        # Handle response_format
        if response_format:
            if isinstance(response_format, type) and issubclass(response_format, BaseModel):
                # Pydantic model class - convert to JSON schema format using serializer
                params['response_format'] = OpenAIChatSerializer.serialize_response_format(response_format)
            elif isinstance(response_format, BaseModel):
                # BaseModel instance - convert to JSON schema format using serializer
                params['response_format'] = OpenAIChatSerializer.serialize_response_format(response_format)
            elif isinstance(response_format, dict):
                # Dict format - use directly
                params['response_format'] = response_format
            else:
                logger.warning(f"Unsupported response_format type: {type(response_format)}")
        
        # Handle streaming
        if stream:
            params['stream'] = True
        
        # Merge additional kwargs
        params.update(kwargs)
        
        return {
            "messages": openai_messages,
            "params": params,
        }

    async def _call_model(self, built: Dict[str, Any]) -> ChatCompletion:
        """Perform one non-streaming API call from a _build_params result."""
        client = self.get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=built["messages"],
            **built["params"],
        )
        return response

    async def _open_stream(self, built: Dict[str, Any]):
        """Open OpenAI's native SSE stream from a _build_params result."""
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")
        params = dict(built["params"])
        params.pop("stream", None)
        params.setdefault("stream_options", {"include_usage": True})
        client = self.get_client()
        return await client.chat.completions.create(
            model=self.model, messages=built["messages"], stream=True, **params
        )

    async def _parse_stream(self, raw):
        """Translate OpenAI chunks → canonical stream events. Unit-testable."""
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

    async def _format_response(
        self,
        response: ChatCompletion,
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
    ) -> Response:
        """Format OpenAI response into Response."""
        try:
            if not response.choices:
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message="No choices in response",
                    data={"raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response)},
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
                    import json
                    try:
                        arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    # Format arguments as keyword arguments
                    if arguments:
                        args_str = ", ".join([f"{k}={v!r}" for k, v in arguments.items()])
                        formatted_lines.append(f"Calling function {name}({args_str})")
                    else:
                        formatted_lines.append(f"Calling function {name}()")
                    
                    functions.append({
                        "name": name,
                        "args": arguments
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
                import json
                try:
                    data = json.loads(content)
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
                except json.JSONDecodeError as e:
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

