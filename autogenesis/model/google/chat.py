from typing import Any, Optional, Union, List, Dict, ClassVar
import httpx

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from pydantic import BaseModel, Field, ConfigDict

import json
from autogenesis.logger import logger
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.types import TokenUsage, BaseChatModel
from autogenesis.message.types import Message, HumanMessage, SystemMessage, AssistantMessage
from autogenesis.model.google.serializer import GoogleChatSerializer
from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool

class ChatGoogle(BaseChatModel):
    """
    A wrapper that provides a unified interface for Google Gemini chat completions.
    
    This class handles Google Gemini API-specific formatting and provides methods for chat completions
    with support for tools and streaming.
    
    Note: Google Gemini uses response_schema for structured outputs.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    supports_true_streaming: bool = True

    # Model configuration
    model: str

    # Model params
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    max_output_tokens: Optional[int] = 8192
    reasoning: Optional[Dict[str, Any]] = None
    
    # Client initialization parameters
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: Optional[Union[float, httpx.Timeout]] = httpx.Timeout(600.0, connect=30.0)
    max_retries: int = 5

    @property
    def provider(self) -> str:
        return 'google'

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    def _client(self):
        """Return a cached async-capable Google GenAI client (the unified ``google-genai``
        SDK; the legacy ``google-generativeai`` was deprecated 2025-11-30)."""
        if genai is None:
            raise ImportError("google-genai package is required. Install it with: pip install google-genai")
        client = getattr(self, "_genai_client", None)
        if client is None:
            http_options = genai_types.HttpOptions(base_url=self.base_url) if self.base_url else None
            client = genai.Client(api_key=self.api_key, http_options=http_options)
            object.__setattr__(self, "_genai_client", client)
        return client

    @property
    def name(self) -> str:
        return str(self.model)

    @staticmethod
    def _usage_dict(u) -> Optional[Dict[str, Any]]:
        """Gemini's ``usage_metadata`` is a protobuf message (no ``model_dump`` / not
        dict-iterable). Pull its token counts into a plain dict — ``TokenUsage.from_raw``
        already understands these ``*_token_count`` keys."""
        if u is None:
            return None
        return {
            "prompt_token_count": getattr(u, "prompt_token_count", 0) or 0,
            "candidates_token_count": getattr(u, "candidates_token_count", 0) or 0,
            "total_token_count": getattr(u, "total_token_count", 0) or 0,
        }

    def _get_usage(self, response) -> Optional[Dict[str, Any]]:
        """Extract usage information from Google Gemini response."""
        if hasattr(response, 'usage_metadata') and response.usage_metadata is not None:
            return self._usage_dict(response.usage_metadata)
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
            - system_instruction: System instruction (if any)
            - contents: Serialized messages
            - generation_config: Generation configuration (temperature, max_output_tokens, etc.)
            - tools: Serialized tools (if any)
            - params: All other API parameters
        """
        # Serialize messages to Google Gemini format
        system_instruction, gemini_contents = GoogleChatSerializer.serialize_messages(messages)

        # Build the GenerateContentConfig kwargs (the new SDK folds generation params,
        # tools, and response schema into one ``config`` object).
        cfg: Dict[str, Any] = {}
        if system_instruction:
            cfg["system_instruction"] = system_instruction
        if self.temperature is not None:
            cfg["temperature"] = self.temperature
        if self.top_p is not None:
            cfg["top_p"] = self.top_p
        if self.top_k is not None:
            cfg["top_k"] = self.top_k
        if self.max_output_tokens is not None:
            cfg["max_output_tokens"] = self.max_output_tokens
        # ``reasoning`` is the OpenRouter-style toggle ({"reasoning": {"enabled": ...}}) —
        # only forward a genuine ``thinking_config`` if one was supplied in that shape
        # (google-genai natively supports thinking_config).
        if self.reasoning:
            tc = self.reasoning.get("thinking_config")
            if tc is not None:
                cfg["thinking_config"] = tc
        if response_format:
            try:
                cfg.update(GoogleChatSerializer.serialize_response_format(response_format))
            except ValueError as e:
                logger.warning(f"Failed to serialize response_format: {e}")
        if tools:
            formatted_tools = GoogleChatSerializer.serialize_tools(tools)
            if formatted_tools:
                cfg["tools"] = formatted_tools

        return {
            "model": str(self.model),
            "contents": gemini_contents,
            "config": cfg,
            "stream": stream,
        }

    def _config_obj(self, cfg: Dict[str, Any]):
        return genai_types.GenerateContentConfig(**cfg) if cfg else None

    async def _call_model(self, built: Dict[str, Any]) -> Any:
        """One non-streaming call via the async google-genai client."""
        client = self._client()
        return await client.aio.models.generate_content(
            model=built["model"],
            contents=built["contents"],
            config=self._config_obj(built.get("config") or {}),
        )

    async def _open_stream(self, built: Dict[str, Any]):
        """Open Gemini's stream — google-genai is natively async, so this returns its
        async iterator of chunks directly (no thread bridging needed)."""
        client = self._client()
        return await client.aio.models.generate_content_stream(
            model=built["model"],
            contents=built["contents"],
            config=self._config_obj(built.get("config") or {}),
        )

    async def _parse_stream(self, raw):
        """Translate Gemini chunks → canonical stream events. Unit-testable."""
        from autogenesis.model.types import TextDelta, ThinkingDelta, ToolCallComplete, StreamDone, normalize_stop_reason

        usage = None
        finish = None
        tool_index = 0
        async for chunk in raw:
            u = getattr(chunk, "usage_metadata", None)
            if u is not None:
                usage = self._usage_dict(u)
            cands = getattr(chunk, "candidates", None) or []
            if not cands:
                continue
            cand = cands[0]
            fr = getattr(cand, "finish_reason", None)
            if fr:
                finish = fr
            content = getattr(cand, "content", None)
            parts = (getattr(content, "parts", None) or []) if content else []
            for part in parts:
                txt = getattr(part, "text", None)
                if txt:
                    # A "thought" part (include_thoughts) is a reasoning summary — route it
                    # to the thinking channel, not the answer text.
                    if getattr(part, "thought", False):
                        yield ThinkingDelta(txt)
                    else:
                        yield TextDelta(txt)
                fc = getattr(part, "function_call", None)
                name = (getattr(fc, "name", "") or "") if fc is not None else ""
                if name:  # a text part carries an empty function_call — skip it
                    args = getattr(fc, "args", {}) or {}
                    try:
                        args = dict(args)  # Gemini args may be a proto Map
                    except Exception:
                        pass
                    yield ToolCallComplete(index=tool_index, id=f"call_{tool_index}", name=name, input=args)
                    tool_index += 1
        fr_name = getattr(finish, "name", None) or (str(finish) if finish is not None else None)
        yield StreamDone(stop_reason=normalize_stop_reason(fr_name), usage=usage)

    async def _format_response(
        self,
        response: Any,
        tools: Optional[List["Tool"]] = None,
        response_format: Optional[Union[Type[BaseModel], BaseModel, Dict]] = None,
    ) -> Response:
        """Format Google Gemini response into Response."""
        try:
            # Handle SDK response object
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
            elif isinstance(response, dict):
                candidates = response.get("candidates", [])
                candidate = candidates[0] if candidates else {}
            else:
                candidate = {}

            if not candidate:
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message="No candidates in response",
                    data={"raw_response": str(response)},
                )

            # Extract content and function calls
            text_parts = []
            thinking_parts = []
            function_calls = []

            if hasattr(candidate, 'content'):
                # SDK response object
                content = candidate.content
                if hasattr(content, 'parts'):
                    parts = content.parts
                else:
                    parts = []
            elif isinstance(candidate, dict):
                # Dict format
                content = candidate.get("content", {})
                parts = content.get("parts", [])
            else:
                parts = []
            
            for part in parts:
                # A Gemini Part protobuf always carries BOTH ``text`` and ``function_call``
                # attributes (empty when unused), so check each by VALUE, not hasattr — else
                # a function-call part (empty text) is misread as text and the call is lost.
                if isinstance(part, dict):
                    txt = part.get("text")
                    fc = part.get("function_call")
                    is_thought = bool(part.get("thought"))
                else:
                    txt = getattr(part, "text", None)
                    fc = getattr(part, "function_call", None)
                    is_thought = bool(getattr(part, "thought", False))
                if txt:
                    # thought parts (include_thoughts) → thinking channel, not the answer
                    (thinking_parts if is_thought else text_parts).append(txt)
                fc_name = (fc.get("name") if isinstance(fc, dict) else getattr(fc, "name", "")) if fc else ""
                if fc_name:
                    fc_args = (fc.get("args") if isinstance(fc, dict) else getattr(fc, "args", {})) or {}
                    try:
                        fc_args = dict(fc_args)  # Gemini args may be a proto Map
                    except Exception:
                        pass
                    function_calls.append({"name": fc_name, "args": fc_args})

            message_text = "\n".join(text_parts) if text_parts else ""
            thinking_text = "\n".join(thinking_parts) if thinking_parts else ""

            usage = self._get_usage(response)
            finish_reason = None
            if hasattr(candidate, 'finish_reason'):
                finish_reason = candidate.finish_reason
            elif isinstance(candidate, dict):
                finish_reason = candidate.get("finish_reason")

            # Handle function calling
            if tools and function_calls:
                formatted_lines = []
                functions = []

                for func_call in function_calls:
                    name = func_call.get("name", "")
                    args_data = func_call.get("args", {})

                    # Format arguments as keyword arguments
                    if args_data:
                        args_str = ", ".join([f"{k}={v!r}" for k, v in args_data.items()])
                        formatted_lines.append(f"Calling function {name}({args_str})")
                    else:
                        formatted_lines.append(f"Calling function {name}()")

                    functions.append({
                        "name": name,
                        "args": args_data
                    })

                formatted_message = "\n".join(formatted_lines)


                return Response(
                    type=ResponseType.LLM,
                    success=True,
                    message=formatted_message,
                    data={
                        "raw_response": str(response),
                        "thinking": thinking_text,
                        "functions": functions,
                        "usage": usage,
                        "finish_reason": finish_reason,
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
                        data={"raw_response": str(response)},
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
                            "raw_response": str(response),
                            "thinking": thinking_text,
                            "usage": usage,
                            "finish_reason": finish_reason,
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
                        "raw_response": str(response),
                        "thinking": thinking_text,
                        "usage": usage,
                        "finish_reason": finish_reason,
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

