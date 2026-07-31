from typing import Any, Optional, Union, List, Dict
import httpx

try:
    from anthropic import AsyncAnthropic, APIError, APIConnectionError, RateLimitError
    try:
        from anthropic import transform_schema
    except ImportError:
        transform_schema = None
except ImportError:
    AsyncAnthropic = None
    APIError = Exception
    APIConnectionError = Exception
    RateLimitError = Exception
    transform_schema = None

from pydantic import BaseModel, Field, ConfigDict



import json
from autogenesis.logger import logger
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage, BaseChatModel
from autogenesis.message.types import Message, HumanMessage, SystemMessage, AssistantMessage
from autogenesis.model.anthropic.serializer import AnthropicChatSerializer
from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool

class ChatAnthropic(BaseChatModel):
    """
    A wrapper that provides a unified interface for Anthropic chat completions.

    Chat/stream orchestration lives in BaseChatModel; this class supplies the
    Anthropic /v1/messages wire details (true SSE streaming). Structured output is
    native ``output_format`` (beta) — hence mode "native". Only register models
    that support output_format in the catalog; callers are expected to request
    structured output only on such models.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    supports_true_streaming: bool = True

    # Model configuration
    model: str

    # Model params
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = None
    max_tokens: Optional[int] = 16384

    # Client initialization parameters
    api_key: Optional[str] = None
    base_url: Optional[Union[str, httpx.URL]] = None
    reasoning: Optional[Dict[str, Any]] = None
    timeout: Optional[Union[float, httpx.Timeout]] = httpx.Timeout(600.0, connect=30.0)
    max_retries: int = 5
    default_headers: Optional[Dict[str, str]] = None
    http_client: Optional[httpx.AsyncClient] = None

    @property
    def provider(self) -> str:
        return 'anthropic'

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    def _get_client_params(self) -> Dict[str, Any]:
        """Prepare client parameters dictionary."""
        # Prepare default headers
        headers = dict(self.default_headers) if self.default_headers else {}
        
        # Add Anthropic beta header for structured outputs support
        if 'anthropic-beta' not in headers:
            headers['anthropic-beta'] = 'structured-outputs-2025-11-13'
        
        base_params = {
            'api_key': self.api_key,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'default_headers': headers if headers else None,
        }
        
        # Add base_url if provided. The SDK appends its own "/v1/messages", so a
        # base that already ends in "/v1" would POST to "/v1/v1/messages" (404).
        # Gateways shared with the OpenAI-compatible providers are configured with
        # the "/v1" suffix, so strip it here rather than requiring a second env var.
        if self.base_url:
            base_params['base_url'] = str(self.base_url).rstrip('/').removesuffix('/v1')
        
        # Add http_client if provided
        if self.http_client is not None:
            base_params['http_client'] = self.http_client
        
        # Create client_params dict with non-None values
        client_params = {k: v for k, v in base_params.items() if v is not None}
        
        return client_params

    def get_client(self) -> AsyncAnthropic:
        """
        Returns an AsyncAnthropic client.

        Returns:
            AsyncAnthropic: An instance of the AsyncAnthropic client.
        """
        if AsyncAnthropic is None:
            raise ImportError("anthropic package is required. Install it with: pip install anthropic")
        
        client_params = self._get_client_params()
        return AsyncAnthropic(**client_params)

    @property
    def name(self) -> str:
        return str(self.model)

    def _get_usage(self, response) -> Optional[Dict[str, Any]]:
        """Extract usage information from Anthropic response."""
        if hasattr(response, 'usage') and response.usage is not None:
            return response.usage.model_dump()
        else:
            return None

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
            - system: System message (if any)
            - messages: Serialized messages
            - params: All other API parameters (tools, temperature, max_tokens, etc.)
        """
        # Serialize messages to Anthropic format
        system_message, anthropic_messages = AnthropicChatSerializer.serialize_messages(messages)
        
        # Build API parameters
        params: Dict[str, Any] = {
            'model': self.model,
            'messages': anthropic_messages,
        }
        
        # Add system message if provided
        if system_message:
            params['system'] = system_message
        
        # Add model parameters
        if self.temperature is not None:
            params['temperature'] = self.temperature
        if self.top_p is not None:
            params['top_p'] = self.top_p
        if self.max_tokens is not None:
            params['max_tokens'] = self.max_tokens
        if self.reasoning is not None:
            # Anthropic native API uses `thinking`, not `reasoning_effort` (OpenRouter/OpenAI concept)
            # Skip `reasoning_effort` — passing it directly causes an unexpected keyword argument error
            anthropic_reasoning = {k: v for k, v in self.reasoning.items() if k != "reasoning_effort"}
            if anthropic_reasoning:
                params.update(anthropic_reasoning)
        
        # Format tools using serializer
        if tools:
            formatted_tools = AnthropicChatSerializer.serialize_tools(tools)
            if formatted_tools:
                params['tools'] = formatted_tools
        
        # Handle response_format (Anthropic uses the beta output_format parameter)
        use_beta_api = False
        if response_format:
            try:
                params['output_format'] = AnthropicChatSerializer.serialize_response_format(response_format)
                use_beta_api = True
            except ValueError as e:
                logger.warning(f"Failed to serialize response_format: {e}")

        # Add betas parameter if using structured outputs
        if use_beta_api:
            params['betas'] = ['structured-outputs-2025-11-13']

        # Streaming: the stream flag is applied by _open_stream (which passes
        # stream=True explicitly), so nothing to set on params here.

        # Merge additional kwargs
        params.update(kwargs)
        
        return {
            "system": system_message,
            "messages": anthropic_messages,
            "params": params,
            "use_beta_api": use_beta_api,
        }

    async def _call_model(self, built: Dict[str, Any]) -> Any:
        """Perform one non-streaming API call from a _build_params result.

        built["params"] already carries model/messages/system; the beta route is
        used when output_format (structured output) was requested.
        """
        client = self.get_client()
        params = built["params"]
        if built.get("use_beta_api"):
            return await client.beta.messages.create(**params)
        return await client.messages.create(**params)

    async def _open_stream(self, built: Dict[str, Any]):
        """Open Anthropic's native SSE stream from a _build_params result."""
        if AsyncAnthropic is None:
            raise ImportError("anthropic package is required. Install it with: pip install anthropic")
        params = dict(built["params"])
        params.pop("stream", None)
        client = self.get_client()
        create = client.beta.messages.create if built.get("use_beta_api") else client.messages.create
        return await create(stream=True, **params)

    async def _parse_stream(self, raw):
        """Translate Anthropic SSE events → canonical stream events. Unit-testable."""
        from autogenesis.model.types import (
            TextDelta, ThinkingDelta, ToolCallStart, ToolCallArgsDelta, StreamDone, normalize_stop_reason,
        )
        usage: Dict[str, Any] = {}
        stop = None
        async for ev in raw:
            t = getattr(ev, "type", None)
            if t == "message_start":
                u = getattr(getattr(ev, "message", None), "usage", None)
                if u is not None:
                    usage.update(u.model_dump() if hasattr(u, "model_dump") else dict(u))
            elif t == "content_block_start":
                cb = getattr(ev, "content_block", None)
                if getattr(cb, "type", None) == "tool_use":
                    yield ToolCallStart(index=ev.index, id=cb.id, name=cb.name)
            elif t == "content_block_delta":
                d = ev.delta
                dt = getattr(d, "type", None)
                if dt == "text_delta":
                    yield TextDelta(d.text)
                elif dt == "thinking_delta":
                    yield ThinkingDelta(d.thinking)
                elif dt == "input_json_delta":
                    yield ToolCallArgsDelta(index=ev.index, partial_json=d.partial_json)
            elif t == "message_delta":
                d = getattr(ev, "delta", None)
                if d is not None and getattr(d, "stop_reason", None):
                    stop = d.stop_reason
                u = getattr(ev, "usage", None)
                if u is not None:
                    usage.update(u.model_dump() if hasattr(u, "model_dump") else dict(u))
        yield StreamDone(stop_reason=normalize_stop_reason(stop), usage=usage or None)

    async def _format_response(
        self,
        response: Any,
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
    ) -> Response:
        """Format Anthropic response into Response."""
        try:
            # Handle SDK response object
            if hasattr(response, 'content'):
                content = response.content
            elif isinstance(response, dict):
                content = response.get("content", [])
            else:
                content = []

            if not content:
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message="No content in response",
                    data={"raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response)},
                )

            # Extract text content and tool calls
            text_parts = []
            tool_calls = []
            
            for item in content:
                if hasattr(item, 'type'):
                    # SDK response object
                    if item.type == "text":
                        text_parts.append(item.text)
                    elif item.type == "tool_use":
                        tool_calls.append({
                            "id": item.id,
                            "name": item.name,
                            "input": item.input,
                        })
                elif isinstance(item, dict):
                    # Dict format
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type == "tool_use":
                        tool_calls.append(item)

            message_text = "\n".join(text_parts) if text_parts else ""

            usage = self._get_usage(response)
            stop_reason = response.stop_reason if hasattr(response, 'stop_reason') else response.get("stop_reason") if isinstance(response, dict) else None

            # Handle function calling
            if tools and tool_calls:
                formatted_lines = []
                functions = []

                for tool_call in tool_calls:
                    name = tool_call.get("name", "")
                    tool_id = tool_call.get("id", "")
                    input_data = tool_call.get("input", {})

                    # Format arguments as keyword arguments
                    if input_data:
                        args_str = ", ".join([f"{k}={v!r}" for k, v in input_data.items()])
                        formatted_lines.append(f"Calling function {name}({args_str})")
                    else:
                        formatted_lines.append(f"Calling function {name}()")

                    functions.append({
                        "id": tool_id,
                        "name": name,
                        "args": input_data
                    })

                formatted_message = "\n".join(formatted_lines)


                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=formatted_message,
                    data={
                        "raw_response": response.model_dump() if hasattr(response, 'model_dump') else response,
                        "functions": functions,
                        "usage": usage,
                        "stop_reason": stop_reason,
                    },
                    usage=TokenUsage.from_raw(usage),
                )

            # Handle structured output (if response_format was provided)
            elif response_format and isinstance(response_format, type) and issubclass(response_format, BaseModel):
                if not message_text:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message="Empty response content from model",
                        data={"raw_response": response},
                    )

                # Try to parse JSON from message text
                import json
                try:
                    data = json.loads(message_text)
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
                            "raw_response": response.model_dump() if hasattr(response, 'model_dump') else response,
                            "usage": usage,
                            "stop_reason": stop_reason,
                        },
                        usage=TokenUsage.from_raw(usage),
                        parsed_model=parsed_model,
                    )
                except json.JSONDecodeError as e:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message=f"Failed to parse JSON from response: {e}",
                        data={"error": str(e), "content": message_text},
                    )
                except Exception as e:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message=f"Failed to validate response against schema: {e}",
                        data={"error": str(e), "content": message_text},
                    )

            # Default: return content as string
            else:

                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=message_text,
                    data={
                        "raw_response": response.model_dump() if hasattr(response, 'model_dump') else response,
                        "usage": usage,
                        "stop_reason": stop_reason,
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