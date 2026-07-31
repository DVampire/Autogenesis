from __future__ import annotations
import json as _json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Type, Union, TYPE_CHECKING
import httpx
from pydantic import BaseModel, ConfigDict, Field
from autogenesis.session import BaseContext

if TYPE_CHECKING:
    from autogenesis.message.types import Message
    from autogenesis.tool.types import Tool


class ModelContext(BaseContext):
    """Context passed into model manager and individual model invocations."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(description="Unique session/call identifier.")
    name: Optional[str] = Field(default=None, description="Human-readable label for this invocation context.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this context.")


class ModelConfig(BaseModel):
    """Configuration container describing a single LLM/provider pairing."""

    model_name: str = Field(description="Human-readable name used across the codebase.")
    model_type: str = Field(description="Model type, e.g. 'chat/completions', 'responses', 'embeddings'.")
    model_id: str = Field(description="Provider-specific identifier passed to the API.")
    provider: str = Field(description="Provider slug, e.g. 'openai', 'anthropic'.")
    api_base: Optional[str] = Field(default=None, description="Override API base URL.")
    api_key: Optional[str] = Field(default=None, description="Override API key.")
    temperature: Optional[float] = Field(default=None, description="Temperature parameter for the model.")
    reasoning: Optional[Dict[str, Any]] = Field(default={
        "reasoning_effort": "high"
    }, description="Reasoning configuration.")
    plugins: Optional[List[Dict[str, Any]]] = Field(default=None, description="Plugins to use for the model.")
    max_completion_tokens: Optional[int] = Field(default=None, description="Maximum completion tokens for chat/completions models.")
    max_output_tokens: Optional[int] = Field(default=None, description="Maximum output tokens for responses API models.")
    supports_streaming: bool = Field(default=True, description="Whether streaming is supported.")
    supports_functions: bool = Field(default=False, description="Whether tool/function calling is supported.")
    supports_vision: bool = Field(default=False, description="Whether multimodal inputs are supported.")
    output_version: Optional[str] = Field(
        default=None,
        description="Optional output schema version when required by provider.",
    )
    timeout: Optional[float] = Field(default=None, description="Request timeout in seconds.")
    key_pool_name: Optional[str] = Field(default=None, description="Key pool name for round-robin key lookup. Defaults to provider if not set.")
    fallback_model: Optional[str] = Field(
        default=None,
        description="Fallback model name to use if the primary model fails due to policy/content filter errors.",
    )


class TokenUsage(BaseModel):
    """Structured token usage from a single LLM API call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost: Optional[float] = None

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_write_tokens + self.cache_read_tokens

    @classmethod
    def from_raw(cls, raw: Optional[Dict[str, Any]]) -> Optional["TokenUsage"]:
        """Normalize provider-specific usage dicts into TokenUsage."""
        if not raw:
            return None
        # cache_read: OpenRouter returns in prompt_tokens_details.cached_tokens
        cache_read = (
            raw.get("cache_read_input_tokens") or
            (raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        )
        # cost: OpenRouter returns top-level cost field
        cost_raw = raw.get("cost")
        cost = float(cost_raw) if cost_raw is not None else None
        return cls(
            input_tokens=(
                raw.get("prompt_tokens") or raw.get("input_tokens") or
                raw.get("prompt_token_count") or 0
            ),
            output_tokens=(
                raw.get("completion_tokens") or raw.get("output_tokens") or
                raw.get("candidates_token_count") or 0
            ),
            cache_write_tokens=raw.get("cache_creation_input_tokens") or 0,
            cache_read_tokens=cache_read,
            cost=cost,
        )

    def summary_line(self, model: str = "") -> str:
        parts = [f"in={self.input_tokens}", f"out={self.output_tokens}"]
        if self.cache_write_tokens:
            parts.append(f"cache_write={self.cache_write_tokens}")
        if self.cache_read_tokens:
            parts.append(f"cache_read={self.cache_read_tokens}")
        if self.cost is not None:
            parts.append(f"cost=${self.cost:.6f}")
        prefix = f"[{model}] " if model else ""
        return f"{prefix}tokens: {', '.join(parts)}"


# ---------------------------------------------------------------------------
# Canonical tool-calling + streaming representation (provider-agnostic)
# ---------------------------------------------------------------------------
# The agent and capability layers only ever see these types. Each provider's
# serializer converts to/from its own wire format (tool_use / tool_calls /
# functionCall; input_json_delta / arguments fragments / whole part), so format
# differences never leak past the provider boundary.


class ToolCall(BaseModel):
    """A normalized 'model wants to call tool X' — input is always a parsed dict."""
    id: str = ""
    name: str = ""
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """A normalized tool result to feed back to the model."""
    tool_call_id: str
    content: str
    is_error: bool = False


# --- canonical stream events (dataclasses = cheap on the hot path) ---
@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class ToolCallStart:
    index: int
    id: str
    name: str


@dataclass
class ToolCallArgsDelta:
    index: int
    partial_json: str


@dataclass
class ToolCallComplete:
    """Whole-part providers (Gemini) emit the tool call in one piece."""
    index: int
    id: str
    name: str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamDone:
    stop_reason: Optional[str] = None          # canonical: tool_use | end_turn | max_tokens | ...
    usage: Optional[Dict[str, Any]] = None     # raw provider usage dict (TokenUsage.from_raw handles it)


StreamEvent = Any  # union of the dataclasses above


def normalize_stop_reason(raw: Optional[str]) -> Optional[str]:
    """Map any provider's finish/stop reason to the canonical vocabulary."""
    if raw is None:
        return None
    r = str(raw).lower()
    if r in ("tool_use", "tool_calls", "function_call"):
        return "tool_use"
    if r in ("end_turn", "stop", "stop_sequence"):
        return "end_turn"
    if r in ("max_tokens", "length", "max_output_tokens"):
        return "max_tokens"
    if r in ("refusal",):
        return "refusal"
    if r in ("pause_turn",):
        return "pause_turn"
    return r


async def accumulate_stream(events: "AsyncIterator[StreamEvent]") -> Dict[str, Any]:
    """Fold a canonical event stream into a buffered result.

    Returns ``{text, thinking, tool_calls: List[ToolCall], stop_reason, usage}``.
    Lets the buffered ``__call__`` path be implemented on top of streaming, and
    lets the agent get a final message after consuming a stream.
    """
    text_parts: List[str] = []
    thinking_parts: List[str] = []
    # index -> {"id","name","args"(str, for fragment providers)|"input"(dict, whole)}
    tools: Dict[int, Dict[str, Any]] = {}
    stop_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None

    async for ev in events:
        if isinstance(ev, TextDelta):
            text_parts.append(ev.text)
        elif isinstance(ev, ThinkingDelta):
            thinking_parts.append(ev.text)
        elif isinstance(ev, ToolCallStart):
            slot = tools.setdefault(ev.index, {"id": "", "name": "", "args": ""})
            if ev.id:
                slot["id"] = ev.id
            if ev.name:
                slot["name"] = ev.name
        elif isinstance(ev, ToolCallArgsDelta):
            slot = tools.setdefault(ev.index, {"id": "", "name": "", "args": ""})
            slot["args"] = slot.get("args", "") + ev.partial_json
        elif isinstance(ev, ToolCallComplete):
            tools[ev.index] = {"id": ev.id, "name": ev.name, "input": ev.input}
        elif isinstance(ev, StreamDone):
            stop_reason = ev.stop_reason
            usage = ev.usage

    tool_calls: List[ToolCall] = []
    for idx in sorted(tools):
        t = tools[idx]
        if "input" in t:                     # whole-part provider
            parsed = t["input"] or {}
        else:                                # fragment provider: join + json.loads
            raw = (t.get("args") or "").strip()
            try:
                parsed = _json.loads(raw) if raw else {}
            except Exception:
                parsed = {"__raw__": raw}
        tool_calls.append(ToolCall(id=t.get("id") or f"call_{idx}", name=t.get("name", ""), input=parsed))

    return {
        "text": "".join(text_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
        "usage": usage,
    }


async def build_response_from_stream(
    events: "AsyncIterator[StreamEvent]",
    *,
    tools: Any = None,
    response_format: Any = None,
    structured_tool_name: Optional[str] = None,
) -> Any:
    """Fold a canonical event stream into a buffered ``Response`` — same shape as
    each provider's ``_format_response`` (functions / parsed_model / plain text).

    This is the single place the streaming path builds a buffered result, so
    ``__call__(stream=True)`` on every provider returns exactly what the
    non-streaming path would. Structured output stays pydantic: when
    ``response_format`` is a ``BaseModel`` subclass, the accumulated text is
    parsed and validated into it and returned as ``Response.parsed_model``.
    """
    from autogenesis.response.types import Response, ResponseType

    acc = await accumulate_stream(events)
    usage = TokenUsage.from_raw(acc.get("usage"))
    stop_reason = acc.get("stop_reason")
    common: Dict[str, Any] = {
        "usage": acc.get("usage"),
        "stop_reason": stop_reason,
        "text": acc.get("text", ""),
        "thinking": acc.get("thinking", ""),
    }

    # 0) Structured output via a synthetic schema-tool. When ``structured_tool_name``
    #    is set (tools were present, so the schema rode along as a tool), structured
    #    output is a tool call of that name, not message content — validate THAT
    #    tool's input into parsed_model (takes priority over the generic function-
    #    call branch below).
    if (structured_tool_name and isinstance(response_format, type)
            and issubclass(response_format, BaseModel)):
        for c in acc["tool_calls"]:
            if c.name == structured_tool_name:
                try:
                    parsed = response_format.model_validate(c.input)
                except Exception as e:
                    msg = (f"Structured output truncated at max_tokens: {e}"
                           if stop_reason == "max_tokens"
                           else f"Structured output failed schema validation: {e}")
                    return Response(type=ResponseType.LLM, success=False, message=msg,
                                    data={**common, "content": c.input})
                model_name = response_format.__name__
                field_lines = [f"{k}={v!r}" for k, v in parsed.model_dump().items()]
                msg = f"Response result:\n\n{model_name}(\n" + ",\n".join(f"    {l}" for l in field_lines) + "\n)"
                return Response(type=ResponseType.LLM, success=True, message=msg,
                                data=common, usage=usage, parsed_model=parsed)

    # 1) Tool calls (native tool calling)
    if tools and acc["tool_calls"]:
        functions = []
        lines = []
        for c in acc["tool_calls"]:
            functions.append({"id": c.id, "name": c.name, "args": c.input})
            if c.input:
                args_str = ", ".join(f"{k}={v!r}" for k, v in c.input.items())
                lines.append(f"Calling function {c.name}({args_str})")
            else:
                lines.append(f"Calling function {c.name}()")
        return Response(
            type=ResponseType.LLM, success=True, message="\n".join(lines),
            data={**common, "functions": functions}, usage=usage,
        )

    # 2) Structured output (pydantic BaseModel → parsed_model)
    if isinstance(response_format, type) and issubclass(response_format, BaseModel):
        text = acc.get("text", "")
        if not text:
            return Response(type=ResponseType.LLM, success=False,
                            message="Empty response content from model", data=common)
        try:
            parsed = response_format.model_validate(_json.loads(text))
        except Exception as e:
            msg = (f"Structured output truncated at max_tokens: {e}"
                   if stop_reason == "max_tokens"
                   else f"Failed to parse structured output: {e}")
            return Response(type=ResponseType.LLM, success=False,
                            message=msg, data={**common, "content": text})
        model_name = response_format.__name__
        field_lines = [f"{k}={v!r}" for k, v in parsed.model_dump().items()]
        msg = f"Response result:\n\n{model_name}(\n" + ",\n".join(f"    {l}" for l in field_lines) + "\n)"
        return Response(type=ResponseType.LLM, success=True, message=msg,
                        data=common, usage=usage, parsed_model=parsed)

    # 3) Plain text
    return Response(type=ResponseType.LLM, success=True, message=acc.get("text", ""),
                    data=common, usage=usage)


async def buffered_response_to_events(response: Any) -> "AsyncIterator[StreamEvent]":
    """Emit canonical stream events from a final buffered ``Response``.

    Graceful-degradation for providers whose client cannot truly stream
    (custom single-POST REST clients): the whole response is delivered at once
    as canonical events, so ``model_manager.stream()`` presents a uniform
    interface across all providers (SDK-backed stream token-by-token; the rest
    emit the full result in one shot).
    """
    data = getattr(response, "data", None) or {}
    reasoning = data.get("reasoning") or data.get("thinking")
    if reasoning:
        yield ThinkingDelta(str(reasoning))
    functions = data.get("functions")
    if functions:
        for i, fn in enumerate(functions):
            yield ToolCallComplete(
                index=i, id=fn.get("id") or f"call_{i}",
                name=fn.get("name", ""), input=fn.get("args") or {},
            )
    else:
        text = data.get("text")
        if text is None:
            text = getattr(response, "message", "") or ""
        if text:
            yield TextDelta(text)
    yield StreamDone(
        stop_reason=normalize_stop_reason(data.get("stop_reason") or data.get("finish_reason")),
        usage=data.get("usage"),
    )


# ---------------------------------------------------------------------------
# Synthetic structured-output tool
# ---------------------------------------------------------------------------


class _StructuredOutputTool:
    """Duck-typed Tool shim carrying a ``function_calling`` dict.

    ``synthetic_tool`` mode projects a ``response_format`` (a pydantic model)
    into one of these and appends it to ``tools``; every provider's
    ``serialize_tools`` reads ``.function_calling`` (falling back to
    ``.name`` / ``.description``), so the shim serializes like any real tool
    without importing ``autogenesis.tool.types``.
    """

    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.function_calling = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }


def _pydantic_tool_parameters(model: type) -> Dict[str, Any]:
    """Bare JSON-Schema object for a pydantic model, usable as a tool's
    ``parameters`` — ``$defs`` are inlined so providers that reject ``$ref``
    (e.g. Gemini) still work."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(o: Any) -> Any:
        if isinstance(o, dict):
            ref = o.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return inline(defs.get(ref.split("/")[-1], {"type": "object"}))
            return {k: inline(v) for k, v in o.items()}
        if isinstance(o, list):
            return [inline(x) for x in o]
        return o

    return inline(schema)


# ---------------------------------------------------------------------------
# BaseChatModel — the contract every provider chat client implements
# ---------------------------------------------------------------------------


class BaseChatModel(BaseModel, ABC):
    """Common contract for every provider chat client — two unified call modes.

    - ``chat``   — non-streaming; structured output is native ``response_format``
      when no tools are passed, or a synthetic schema-tool when tools are (see
      the structured-output helpers below).
    - ``stream`` — streaming + function calling + structured output; yields the
      canonical stream events above. True-streaming providers override
      ``_open_stream`` / ``_parse_stream``; the rest set
      ``supports_true_streaming = False`` and fall back to buffering ``chat`` and
      replaying it through ``buffered_response_to_events``.

    ``__call__`` is an alias of ``chat`` (with a legacy ``stream=True`` shortcut
    that folds a stream into a buffered ``Response``) so existing callers keep
    working unchanged.

    A provider subclass implements only the wire details — ``_build_params``,
    ``_call_model``, ``_format_response``, and (when truly streaming)
    ``_open_stream`` / ``_parse_stream``. This base owns the orchestration so the
    two modes stay consistent across every provider.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    # Providers that truly stream override _open_stream / _parse_stream; the rest
    # set this False and fall back to buffering chat() and replaying it as events.
    supports_true_streaming: bool = True

    # ---- identity ----
    @property
    def provider(self) -> str:
        return "base"

    @property
    def name(self) -> str:
        return str(getattr(self, "model", ""))

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key

    # ---- structured output ----
    # There is no mode flag: how structured output is done is DERIVED from whether
    # the caller also passes tools. With tools present, native response_format and
    # native tool calling can't coexist in one request, so the schema rides along
    # as a synthetic tool; with no tools, native structured output is used.
    @staticmethod
    def _schema_model(response_format) -> Optional[type]:
        """The pydantic model behind a ``response_format`` (class or instance), else None."""
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            return response_format
        if isinstance(response_format, BaseModel):
            return type(response_format)
        return None

    def _structured_tool_name(self, tools, response_format) -> Optional[str]:
        """Name of the synthetic structured-output tool (the schema model's name),
        or None when structured output is native. Non-None iff ``response_format``
        is a pydantic model AND real ``tools`` are present."""
        m = self._schema_model(response_format)
        return m.__name__ if (m and tools) else None

    def _structured_output(self, tools, response_format):
        """Derive the mechanism from whether tools are present: with tools, project
        ``response_format`` into a synthetic tool and clear ``response_format``;
        with no tools, leave it native. Returns ``(tools, response_format, tool_name)``
        — ``tool_name`` is non-None only on the synthetic path."""
        name = self._structured_tool_name(tools, response_format)
        if not name:
            return tools, response_format, None
        model = self._schema_model(response_format)
        synthetic = _StructuredOutputTool(
            name=name,
            description=(model.__doc__ or f"Return the result as {name}.").strip(),
            parameters=_pydantic_tool_parameters(model),
        )
        return list(tools) + [synthetic], None, name

    def _fold_structured_functions(self, response, response_format, tool_name):
        """Fold the synthetic tool's call (in ``response.data['functions']``) into
        ``parsed_model`` — the non-streaming counterpart of
        ``build_response_from_stream``'s synthetic-tool branch. Shape-identical to
        the native structured branch (drops the tool-call-only ``functions`` key)."""
        from autogenesis.response.types import Response, ResponseType

        model = self._schema_model(response_format)
        if model is None or not getattr(response, "success", False):
            return response
        for fn in (getattr(response, "data", None) or {}).get("functions") or []:
            if fn.get("name") != tool_name:
                continue
            args = fn.get("args", fn.get("arguments")) or {}
            if isinstance(args, str):
                try:
                    args = _json.loads(args)
                except Exception:
                    args = {}
            try:
                parsed = model.model_validate(args)
            except Exception as e:
                return Response(type=ResponseType.LLM, success=False,
                                message=f"Structured output failed schema validation: {e}",
                                data={**(response.data or {}), "content": args})
            field_lines = [f"{k}={v!r}" for k, v in parsed.model_dump().items()]
            msg = (f"Response result:\n\n{model.__name__}(\n"
                   + ",\n".join(f"    {l}" for l in field_lines) + "\n)")
            data = {k: v for k, v in (response.data or {}).items() if k != "functions"}
            return Response(type=ResponseType.LLM, success=True, message=msg,
                            data=data, usage=response.usage, parsed_model=parsed)
        return response  # model called a real tool instead — leave as function calls

    # ---- provider wire details (subclasses implement) ----
    @abstractmethod
    async def _build_params(self, messages, tools=None, response_format=None,
                            stream: bool = False, **kwargs) -> Dict[str, Any]:
        """Serialize messages/tools/response_format into a provider-specific dict."""
        ...

    @abstractmethod
    async def _call_model(self, built: Dict[str, Any]) -> Any:
        """Perform ONE non-streaming API call from a ``_build_params`` result."""
        ...

    @abstractmethod
    async def _format_response(self, response, tools=None, response_format=None):
        """Fold a raw provider response into a ``Response``."""
        ...

    async def _open_stream(self, built: Dict[str, Any]) -> Any:
        """Open the provider's native streaming response. Required only when
        ``supports_true_streaming`` is True."""
        raise NotImplementedError(f"{type(self).__name__}._open_stream not implemented")

    def _parse_stream(self, raw) -> "AsyncIterator[Any]":
        """Translate the provider's native stream into canonical events. Required
        only when ``supports_true_streaming`` is True."""
        raise NotImplementedError(f"{type(self).__name__}._parse_stream not implemented")

    # ---- unified orchestration (shared by all providers) ----
    async def chat(self, messages, tools=None, response_format=None, **kwargs):
        """Non-streaming call. Structured output is native when no tools are passed,
        or a synthetic schema-tool (folded into parsed_model) when tools are."""
        from autogenesis.logger import logger
        from autogenesis.response.types import Response, ResponseType
        tools, effective_rf, tool_name = self._structured_output(tools, response_format)
        try:
            built = await self._build_params(
                messages, tools=tools, response_format=effective_rf, stream=False, **kwargs)
            raw = await self._call_model(built)
            resp = await self._format_response(raw, tools=tools, response_format=effective_rf)
            return self._fold_structured_functions(resp, response_format, tool_name) if tool_name else resp
        except httpx.TimeoutException:
            raise  # the context layer owns retry / fallback on timeout
        except Exception as e:
            logger.error(f"| 🔴 {self.provider} chat error (model={self.name}): {type(e).__name__}: {e}")
            return Response(type=ResponseType.LLM, success=False,
                            message=f"{type(e).__name__}: {e}",
                            data={"error": str(e), "model": self.name})

    async def stream(self, messages, tools=None, response_format=None, **kwargs):
        """Streaming + function calling + structured output; yields canonical events."""
        if not self.supports_true_streaming:
            # Graceful degradation: buffer one chat() call (which derives + folds
            # structured output itself), replay it as events.
            resp = await self.chat(messages, tools=tools, response_format=response_format, **kwargs)
            async for ev in buffered_response_to_events(resp):
                yield ev
            return
        # With tools the schema becomes a tool call; the caller folds it into
        # parsed_model via build_response_from_stream's synthetic branch.
        tools, effective_rf, _ = self._structured_output(tools, response_format)
        built = await self._build_params(
            messages, tools=tools, response_format=effective_rf, stream=True, **kwargs)
        raw = await self._open_stream(built)
        async for ev in self._parse_stream(raw):
            yield ev

    async def __call__(self, messages, tools=None, response_format=None,
                       stream: bool = False, **kwargs):
        """Alias of ``chat``. ``stream=True`` folds the stream into a buffered
        ``Response`` (kept for backward compatibility with existing callers)."""
        if stream:
            return await build_response_from_stream(
                self.stream(messages, tools=tools, response_format=response_format, **kwargs),
                tools=tools, response_format=response_format,
                structured_tool_name=self._structured_tool_name(tools, response_format),
            )
        return await self.chat(messages, tools=tools, response_format=response_format, **kwargs)


__all__ = [
    "ModelContext", "ModelConfig", "TokenUsage",
    "ToolCall", "ToolResult",
    "TextDelta", "ThinkingDelta", "ToolCallStart", "ToolCallArgsDelta",
    "ToolCallComplete", "StreamDone", "StreamEvent",
    "normalize_stop_reason", "accumulate_stream", "build_response_from_stream",
    "buffered_response_to_events", "BaseChatModel",
]
