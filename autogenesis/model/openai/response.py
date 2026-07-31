from collections.abc import Iterable, Mapping
from typing import Any, Literal, Optional, Union, List, Dict, Type
import httpx

try:
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
    from openai.types.shared.chat_model import ChatModel
    from openai.types.shared_params.reasoning_effort import ReasoningEffort
except ImportError:
    # Fallback if openai package is not available
    AsyncOpenAI = None
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception
    ChatModel = str
    ReasoningEffort = str

from pydantic import BaseModel, Field, ConfigDict

from autogenesis.message.types import Message
from autogenesis.model.openai.serializer import OpenAIResponseSerializer, OpenAIChatSerializer
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage
from autogenesis.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool


class ResponseOpenAI(BaseModel):
    """
    A wrapper around AsyncOpenAI that provides a unified interface for OpenAI responses API.
    
    This class is specifically designed for GPT-5 and o-series models that use the responses API endpoint.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    # Model configuration
    model: Union[ChatModel, str]

    # Model params for responses API
    reasoning: Optional[Dict[str, Any]] = None
    max_output_tokens: Optional[int] = 16384
    temperature: Optional[float] = None  # Not used for reasoning models, but kept for compatibility

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

    def _get_usage(self, response: Any) -> Optional[Dict[str, Any]]:
        """Extract usage information from responses API response."""
        usage = None
        try:
            if hasattr(response, 'usage') and response.usage is not None:
                usage_obj = response.usage
                
                # Responses API uses input_tokens and output_tokens instead of prompt_tokens and completion_tokens
                input_tokens = getattr(usage_obj, 'input_tokens', None)
                output_tokens = getattr(usage_obj, 'output_tokens', None)
                total_tokens = getattr(usage_obj, 'total_tokens', None)
                
                # Fallback to prompt_tokens/completion_tokens if input_tokens/output_tokens not available
                if input_tokens is None:
                    input_tokens = getattr(usage_obj, 'prompt_tokens', 0)
                if output_tokens is None:
                    output_tokens = getattr(usage_obj, 'completion_tokens', 0)
                if total_tokens is None:
                    total_tokens = getattr(usage_obj, 'total_tokens', 0)
                
                usage = {
                    'prompt_tokens': input_tokens,
                    'completion_tokens': output_tokens,
                    'total_tokens': total_tokens,
                }
                
                # Handle reasoning tokens if available
                if hasattr(usage_obj, 'output_tokens_details'):
                    details = usage_obj.output_tokens_details
                    if details and hasattr(details, 'reasoning_tokens'):
                        reasoning_tokens = details.reasoning_tokens
                        if reasoning_tokens is not None:
                            usage['reasoning_tokens'] = reasoning_tokens
                elif hasattr(usage_obj, 'completion_tokens_details'):
                    # Fallback to completion_tokens_details
                    details = usage_obj.completion_tokens_details
                    if details and hasattr(details, 'reasoning_tokens'):
                        reasoning_tokens = details.reasoning_tokens
                        if reasoning_tokens is not None:
                            usage['reasoning_tokens'] = reasoning_tokens
                
                # Handle cached tokens if available
                if hasattr(usage_obj, 'input_tokens_details'):
                    prompt_details = usage_obj.input_tokens_details
                    if prompt_details and hasattr(prompt_details, 'cached_tokens'):
                        usage['prompt_cached_tokens'] = prompt_details.cached_tokens
                elif hasattr(usage_obj, 'prompt_tokens_details'):
                    # Fallback to prompt_tokens_details
                    prompt_details = usage_obj.prompt_tokens_details
                    if prompt_details and hasattr(prompt_details, 'cached_tokens'):
                        usage['prompt_cached_tokens'] = prompt_details.cached_tokens
        except (AttributeError, TypeError) as e:
            logger.debug(f"Error extracting usage: {e}")
            pass
        
        return usage

    def _get_reasoning(self, response: Any) -> Optional[str]:
        """Extract reasoning information from responses API response."""
        reasoning = None
        try:
            # Responses API may have reasoning in different places
            if hasattr(response, 'output') and response.output is not None:
                # Check output for reasoning
                output = response.output
                if isinstance(output, list):
                    for item in output:
                        # Handle both object attributes and dict access
                        item_type = None
                        if hasattr(item, 'type'):
                            item_type = item.type
                        elif isinstance(item, dict):
                            item_type = item.get('type')
                        
                        if item_type == 'reasoning':
                            # Try to get content from various possible fields
                            if hasattr(item, 'content') and item.content:
                                reasoning = item.content
                                break
                            elif isinstance(item, dict) and item.get('content'):
                                reasoning = item.get('content')
                                break
                            elif hasattr(item, 'text') and item.text:
                                reasoning = item.text
                                break
                            elif isinstance(item, dict) and item.get('text'):
                                reasoning = item.get('text')
                                break
                            elif hasattr(item, 'summary') and item.summary:
                                reasoning = item.summary
                                break
                            elif isinstance(item, dict) and item.get('summary'):
                                reasoning = item.get('summary')
                                break
                            
                            # If reasoning type found but no content, set to None
                            if reasoning is None:
                                reasoning = None
                                break
                elif isinstance(output, dict):
                    if output.get('type') == 'reasoning':
                        reasoning = output.get('content') or output.get('text') or output.get('summary') or None
            
            # Also check for reasoning_details
            if reasoning is None and hasattr(response, 'reasoning_details'):
                reasoning_details = response.reasoning_details
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
        except (AttributeError, KeyError, TypeError, IndexError) as e:
            logger.debug(f"Error extracting reasoning: {e}")
            pass
        
        return reasoning

    def _extract_output_text(self, response: Any) -> str:
        """Extract output text from responses API response."""
        text = ""
        try:
            # Try output_text attribute first
            if hasattr(response, 'output_text') and response.output_text is not None:
                return response.output_text
            
            # Try output attribute
            if hasattr(response, 'output') and response.output is not None:
                output = response.output
                if isinstance(output, list):
                    for item in output:
                        if hasattr(item, 'type'):
                            if item.type == 'message':
                                if hasattr(item, 'content'):
                                    content = item.content
                                    if isinstance(content, list):
                                        for content_item in content:
                                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                                if hasattr(content_item, 'text'):
                                                    return content_item.text
                                            elif isinstance(content_item, dict) and content_item.get('type') == 'output_text':
                                                return content_item.get('text', '')
                        elif isinstance(item, dict):
                            if item.get('type') == 'message':
                                content = item.get('content', [])
                                for content_item in content:
                                    if content_item.get('type') == 'output_text':
                                        return content_item.get('text', '')
                elif isinstance(output, dict):
                    if output.get('type') == 'message':
                        content = output.get('content', [])
                        for content_item in content:
                            if content_item.get('type') == 'output_text':
                                return content_item.get('text', '')
        except (AttributeError, KeyError, TypeError, IndexError):
            pass
        
        return text

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
            tools: Optional list of Tool instances (may not be supported in responses API)
            response_format: Optional response format (Pydantic model class, instance or dict)
            stream: Whether to stream the response (may not be supported in responses API)
            **kwargs: Additional parameters
            
        Returns:
            Dictionary containing:
            - input: Serialized messages for responses API
            - params: All other API parameters (reasoning, max_output_tokens, response_format, etc.)
        """
        # Serialize messages to responses API format
        input_messages = OpenAIResponseSerializer.serialize_messages(messages)
        
        # Build API parameters
        params: Dict[str, Any] = {
            "model": self.model,
            "input": input_messages,
        }
        
        # Add reasoning for responses API
        # Chat Completions format {"reasoning_effort": "high"} → Responses API format {"reasoning": {"effort": "high"}}
        if self.reasoning is not None:
            if "reasoning_effort" in self.reasoning:
                params["reasoning"] = {"effort": self.reasoning["reasoning_effort"]}
            else:
                params.update(self.reasoning)
        
        # Add max_output_tokens if specified
        if self.max_output_tokens is not None:
            params["max_output_tokens"] = self.max_output_tokens
        
        # Handle response_format (responses API uses text.format with flat structure)
        if response_format:
            if isinstance(response_format, type) and issubclass(response_format, BaseModel):
                # Pydantic model class - convert to responses API format
                # Responses API format: text.format = {type, name, strict, schema}
                # (not nested json_schema like chat completions)
                json_schema = response_format.model_json_schema()
                # Use serializer to optimize schema (add additionalProperties: false)
                optimized = OpenAIChatSerializer.serialize_response_format(response_format)
                # Extract schema from optimized format
                schema = optimized['json_schema']['schema']

                # Honor the serializer's strict decision: it disables strict when the
                # schema contains an open object (Dict[str, Any]), which strict mode
                # forbids. Hardcoding strict=True here would re-introduce the 400.
                params["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": response_format.__name__,
                        "strict": optimized['json_schema'].get('strict', True),
                        "schema": schema
                    }
                }
            elif isinstance(response_format, BaseModel):
                # BaseModel instance - convert to responses API format
                model_class = type(response_format)
                optimized = OpenAIChatSerializer.serialize_response_format(model_class)
                schema = optimized['json_schema']['schema']

                params["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": model_class.__name__,
                        "strict": optimized['json_schema'].get('strict', True),
                        "schema": schema
                    }
                }
            elif isinstance(response_format, dict):
                # Dict format - check if it's already in text.format format
                if "text" in response_format:
                    # Already in text.format format
                    params["text"] = response_format["text"]
                elif "type" in response_format and "name" in response_format and "schema" in response_format:
                    # Already in responses API text.format format (flat structure)
                    params["text"] = {
                        "format": response_format
                    }
                elif "type" in response_format and "json_schema" in response_format:
                    # Chat completions format - convert to responses API format
                    json_schema_obj = response_format["json_schema"]
                    params["text"] = {
                        "format": {
                            "type": "json_schema",
                            "name": json_schema_obj.get("name", "response"),
                            "strict": json_schema_obj.get("strict", True),
                            "schema": json_schema_obj.get("schema", {})
                        }
                    }
                else:
                    # Assume it's a schema dict - wrap it
                    params["text"] = {
                        "format": {
                            "type": "json_schema",
                            "name": "response",
                            "strict": True,
                            "schema": response_format
                        }
                    }
            else:
                logger.warning(f"Unsupported response_format type: {type(response_format)}")
        
        # Note: tools and stream may not be supported in responses API
        if tools:
            logger.warning("Tools may not be supported in responses API")
            # params["tools"] = tools  # Uncomment if supported
        
        if stream:
            logger.warning("Streaming may not be supported in responses API")
            # params["stream"] = True  # Uncomment if supported
        
        # Merge additional kwargs
        params.update(kwargs)
        
        return {
            "input": input_messages,
            "params": params,
        }

    async def _call_model(
        self,
        input_messages: List[Dict[str, Any]],
        **params: Any,
    ) -> Any:
        """
        Call the model API (Step 2).
        
        Unified interface for calling the responses API.
        
        Args:
            input_messages: Serialized messages for responses API
            **params: API parameters
            
        Returns:
            Response object from responses API
        """
        client = self.get_client()
        response = await client.responses.create(**params)
        
        return response

    async def __call__(
        self,
        messages: List[Message],
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Response:
        """
        Execute asynchronous completion call via OpenAI responses API.

        Args:
            messages: List of Message objects (HumanMessage, SystemMessage, AssistantMessage)
            tools: Optional list of Tool instances (may not be supported in responses API)
            response_format: Optional response format (Pydantic model class, instance or dict)
            stream: Whether to stream the response (may not be supported in responses API)
            **kwargs: Additional parameters

        Returns:
            Response with formatted message
        """
        if AsyncOpenAI is None:
            raise ImportError("openai package is required. Install it with: pip install openai")

        try:
            params = await self._build_params(
                messages=messages,
                tools=tools,
                response_format=response_format,
                stream=stream,
                **kwargs,
            )
            
            response = await self._call_model(
                input_messages=params["input"],
                **params["params"],
            )
            
            return await self._format_response(
                response=response,
                tools=tools,
                response_format=response_format,
            )

        except RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Rate limit error: {e.message}",
                data={"error": str(e), "model": self.name},
            )
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API connection error: {str(e)}",
                data={"error": str(e), "model": self.name},
            )
        except APIStatusError as e:
            logger.error(f"API status error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"API status error: {e.message}",
                data={"error": str(e), "status_code": e.status_code, "model": self.name},
            )
        except httpx.TimeoutException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Unexpected error: {str(e)}",
                data={"error": str(e), "model": self.name},
            )

    async def _format_response(
        self,
        response: Any,
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
    ) -> Response:
        """Format OpenAI responses API response into Response."""
        try:
            usage = self._get_usage(response)
            reasoning = self._get_reasoning(response)
            output_text = self._extract_output_text(response)

            # Handle structured output
            if response_format and isinstance(response_format, type) and issubclass(response_format, BaseModel):
                if not output_text:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message="Empty response content from model",
                        data={"raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response)},
                    )
                
                # Parse JSON content
                import json
                try:
                    data = json.loads(output_text)
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
                        data={"error": str(e), "content": output_text},
                    )
                except Exception as e:
                    return Response(
                        type=ResponseType.LLM,
                        success=False,
                        message=f"Failed to validate response against schema: {e}",
                        data={"error": str(e), "content": output_text},
                    )

            # Default: return content as string
            else:
                
                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=output_text,
                    data={
                        "raw_response": response.model_dump() if hasattr(response, 'model_dump') else str(response),
                        "usage": usage,
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

