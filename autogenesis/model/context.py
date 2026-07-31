"""Model context manager — ApiKeyPool + ModelContextManager.

Contains all model registration, client lifecycle, and invocation logic.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv(verbose=True)

from pydantic import BaseModel

from autogenesis.model.types import ModelContext, ModelConfig
from autogenesis.response.types import Response, ResponseType
from autogenesis.model.openai.chat import ChatOpenAI
from autogenesis.model.openai.response import ResponseOpenAI
from autogenesis.model.openai.transcribe import TranscribeOpenAI
from autogenesis.model.openai.embedding import EmbeddingOpenAI
from autogenesis.model.openrouter.chat import ChatOpenRouter
from autogenesis.model.anthropic.chat import ChatAnthropic
from autogenesis.model.google.chat import ChatGoogle
from autogenesis.message.types import Message
from autogenesis.logger import logger
from autogenesis.utils import hvac_client

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool


# ---------------------------------------------------------------------------
# ApiKeyPool
# ---------------------------------------------------------------------------


class ApiKeyPool:
    """Thread-safe round-robin API key pool.

    Each provider registers its key env-var (which may be a single key or a
    comma-separated list) and an optional base-URL env-var. Callers obtain the
    next key via `get_key(provider)`.
    """

    def __init__(self):
        self._keys: Dict[str, List[str]] = {}
        self._bases: Dict[str, Optional[str]] = {}
        self._indices: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_keys(env_var: str) -> List[str]:
        raw = hvac_client.get(env_var)
        return [k.strip() for k in raw.split(",") if k.strip()]

    def register(
        self,
        provider: str,
        key_env: str,
        base_env: Optional[str] = None,
        default_base: Optional[str] = None,
    ) -> "ApiKeyPool":
        self._keys[provider] = self._parse_keys(key_env)
        self._bases[provider] = (
            (hvac_client.get(base_env) or default_base) if base_env else default_base
        )
        self._indices[provider] = 0
        return self

    async def get_base(self, provider: str) -> Optional[str]:
        return self._bases.get(provider)

    async def get_key(self, provider: str) -> Optional[str]:
        async with self._lock:
            keys = self._keys.get(provider, [])
            if not keys:
                return None
            idx = self._indices.get(provider, 0)
            key = keys[idx]
            self._indices[provider] = (idx + 1) % len(keys)
            return key


# ---------------------------------------------------------------------------
# ModelContextManager
# ---------------------------------------------------------------------------


class ModelContextManager:
    """Central registry and invoker for all LLM models.

    Responsibilities:
    1. Register and store model configurations.
    2. Manage provider API-key pools.
    3. Provide a unified invocation interface with retry + fallback.
    """

    def __init__(self):
        self.models: Dict[str, ModelConfig] = {}
        self.model_clients: Dict[str, Any] = {}
        self._key_pool = ApiKeyPool()
        self._current_caller: Optional[str] = None

        # Defaults
        self.max_tokens: int = 32768
        self.default_temperature: float = 0.7
        self.default_timeout: float = 600.0
        self.default_reasoning: Dict[str, Any] = {"reasoning_effort": "high"}
        self.default_plugins: Optional[List[Dict[str, Any]]] = [
            {"id": "file-parser", "pdf": {"engine": "mistral-ocr"}},
            {"id": "web", "max_results": 10},
            {"id": "response-healing"},
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        (
            self._key_pool.register("openai", "OPENAI_API_KEY", "OPENAI_API_BASE", "")
            .register("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_API_BASE", "")
            .register("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE", "")
            .register("google", "GOOGLE_API_KEY", "GOOGLE_API_BASE", "")
        )
        await self._initialize_openai_models()
        await self._initialize_openrouter_models()
        await self._initialize_anthropic_models()
        await self._initialize_google_models()
        logger.info(
            f"| Model context manager initialized with {len(self.models)} models."
        )

    # ------------------------------------------------------------------
    # Provider initialization
    # ------------------------------------------------------------------

    async def _initialize_openai_models(self):
        from autogenesis.model.config import openai_models
        specs = openai_models(
            max_tokens=self.max_tokens,
            default_temperature=self.default_temperature,
            default_reasoning=self.default_reasoning,
        )
        chat_models = specs["chat"]
        response_models = specs["response"]
        transcribe_models = specs["transcribe"]
        embedding_models = specs["embedding"]

        api_base = await self._key_pool.get_base("openai")
        api_key = await self._key_pool.get_key("openai")

        for m in chat_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="openai",
                key_pool_name="openai",
                api_base=api_base,
                api_key=api_key,
                temperature=m.get("temperature"),
                max_completion_tokens=m.get("max_completion_tokens"),
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

        for m in response_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="openai",
                key_pool_name="openai",
                api_base=api_base,
                api_key=api_key,
                reasoning=m.get("reasoning"),
                max_output_tokens=m.get("max_output_tokens"),
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=False,
                supports_functions=False,
                supports_vision=True,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

        for m in transcribe_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="openai",
                key_pool_name="openai",
                api_base=api_base,
                api_key=api_key,
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=False,
                supports_functions=False,
                supports_vision=False,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

        for m in embedding_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="openai",
                key_pool_name="openai",
                api_base=api_base,
                api_key=api_key,
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=False,
                supports_functions=False,
                supports_vision=False,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

    async def _initialize_openrouter_models(self):
        from autogenesis.model.config import openrouter_models
        specs = openrouter_models(
            max_tokens=self.max_tokens,
            default_temperature=self.default_temperature,
            default_timeout=self.default_timeout,
            default_plugins=self.default_plugins,
            default_reasoning=self.default_reasoning,
        )
        chat_models = specs["chat"]

        api_base = await self._key_pool.get_base("openrouter")
        api_key = await self._key_pool.get_key("openrouter")

        for m in chat_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="openrouter",
                key_pool_name="openrouter",
                api_base=api_base,
                api_key=api_key,
                reasoning=m.get("reasoning") or None,
                plugins=m.get("plugins") or None,
                temperature=m.get("temperature"),
                max_completion_tokens=m.get("max_completion_tokens"),
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

    async def _initialize_anthropic_models(self):
        from autogenesis.model.config import anthropic_models
        specs = anthropic_models(
            max_tokens=self.max_tokens,
            default_temperature=self.default_temperature,
            default_timeout=self.default_timeout,
            default_plugins=self.default_plugins,
            default_reasoning=self.default_reasoning,
        )
        chat_models = specs["chat"]

        api_base = await self._key_pool.get_base("anthropic")
        api_key = await self._key_pool.get_key("anthropic")

        for m in chat_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="anthropic",
                key_pool_name="anthropic",
                api_base=api_base,
                api_key=api_key,
                temperature=m.get("temperature"),
                max_completion_tokens=m.get("max_completion_tokens"),
                timeout=m.get("timeout", self.default_timeout),
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                output_version=None,
                fallback_model=m.get("fallback_model"),
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

    async def _initialize_google_models(self):
        _r = lambda: {"reasoning": {"enabled": True}}
        from autogenesis.model.config import google_models
        specs = google_models(max_tokens=self.max_tokens, default_temperature=self.default_temperature, default_timeout=self.default_timeout, default_plugins=self.default_plugins, default_reasoning=self.default_reasoning)
        chat_models = specs["chat"]

        api_base = await self._key_pool.get_base("google")
        api_key = await self._key_pool.get_key("google")

        for m in chat_models:
            cfg = ModelConfig(
                model_name=m["model_name"],
                model_id=m["model_id"],
                model_type=m["model_type"],
                provider="google",
                key_pool_name="google",
                api_base=api_base,
                api_key=api_key,
                reasoning=m.get("reasoning") or None,
                temperature=m.get("temperature"),
                max_completion_tokens=m.get("max_completion_tokens"),
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                output_version=None,
                fallback_model=None,
            )
            self.models[cfg.model_name] = cfg
            await self._create_client(cfg)

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    async def _create_client(self, config: ModelConfig) -> None:
        self.model_clients[config.model_name] = await self._build_client(config)
        logger.info(f"| Created client for {config.model_name}")

    async def _build_client(self, config: ModelConfig):
        if config.provider == "openrouter":
            if config.model_type == "chat/completions":
                return ChatOpenRouter(
                    model=config.model_id,
                    api_key=config.api_key,
                    base_url=config.api_base,
                    reasoning=config.reasoning or None,
                    plugins=config.plugins or None,
                    temperature=config.temperature or self.default_temperature,
                    max_completion_tokens=config.max_completion_tokens
                    or self.max_tokens,
                )
            raise ValueError(
                f"Unsupported model type {config.model_type} for OpenRouter provider"
            )
        elif config.provider == "anthropic":
            if config.model_type == "chat/completions":
                return ChatAnthropic(
                    model=config.model_id,
                    api_key=config.api_key,
                    base_url=config.api_base,
                    reasoning=config.reasoning or None,
                    # Passed through as-is: newer models (opus-4.8, fable-5) reject
                    # `temperature` outright, and their catalog entries omit it so the
                    # parameter is left off the request rather than defaulted to 0.7.
                    temperature=config.temperature,
                    max_tokens=config.max_completion_tokens or self.max_tokens,
                )
            raise ValueError(
                f"Unsupported model type {config.model_type} for Anthropic provider"
            )
        elif config.provider == "google":
            if config.model_type == "chat/completions":
                return ChatGoogle(
                    model=config.model_id,
                    api_key=config.api_key,
                    base_url=config.api_base or None,
                    reasoning=config.reasoning or None,
                    temperature=config.temperature or self.default_temperature,
                    max_output_tokens=config.max_completion_tokens or self.max_tokens,
                )
            raise ValueError(
                f"Unsupported model type {config.model_type} for Google provider"
            )
        elif config.model_type == "responses":
            return ResponseOpenAI(
                model=config.model_id,
                api_key=config.api_key,
                base_url=config.api_base,
                reasoning=config.reasoning or None,
                max_output_tokens=config.max_output_tokens or self.max_tokens,
            )
        elif config.model_type == "transcriptions":
            return TranscribeOpenAI(
                model=config.model_id, api_key=config.api_key, base_url=config.api_base
            )
        elif config.model_type == "embeddings":
            return EmbeddingOpenAI(
                model=config.model_id, api_key=config.api_key, base_url=config.api_base
            )
        else:
            return ChatOpenAI(
                model=config.model_id,
                api_key=config.api_key,
                base_url=config.api_base,
                temperature=config.temperature or self.default_temperature,
                reasoning=config.reasoning or None,
                max_completion_tokens=config.max_completion_tokens or self.max_tokens,
            )

    async def _get_client(self, model: str):
        client = self.model_clients.get(model)
        if client:
            model_config = self.models.get(model)
            pool_name = (
                (model_config.key_pool_name or model_config.provider)
                if model_config
                else None
            )
            key = await self._key_pool.get_key(pool_name) if pool_name else None
            if key:
                client.set_api_key(key)
        return client

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_model(self, config: ModelConfig) -> None:
        if config.provider not in [
            "openai",
            "openrouter",
            "anthropic",
            "google",
        ]:
            raise ValueError(f"Unsupported provider: {config.provider}")
        self.models[config.model_name] = config
        await self._create_client(config)
        logger.info(f"Registered model: {config.model_name}")

    async def unregister_model(self, model_name: str) -> bool:
        """Remove a runtime model registration and its cached client."""
        existed = model_name in self.models
        self.models.pop(model_name, None)
        self.model_clients.pop(model_name, None)
        if existed:
            logger.info(f"Unregistered model: {model_name}")
        return existed

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_model_config(self, model: str) -> Optional[ModelConfig]:
        return self.models.get(model)

    def list(self) -> List[str]:
        return list(self.models.keys())

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    def _log_usage(self, model_name: str, result: Response) -> None:
        if not result.success:
            return
        # Prefer the structured TokenUsage field; fall back to raw dict for older code paths
        usage = result.usage
        if usage is None and result.data:
            from autogenesis.model.types import TokenUsage

            raw = (result.data or {}).get("usage")
            usage = TokenUsage.from_raw(raw) if raw else None
        if usage is None:
            return
        parts = [
            f"model={model_name}",
            f"in={usage.input_tokens}",
            f"out={usage.output_tokens}",
            f"total={usage.total}",
        ]
        if usage.cache_write_tokens:
            parts.append(f"cache_write={usage.cache_write_tokens}")
        if usage.cache_read_tokens:
            parts.append(f"cache_read={usage.cache_read_tokens}")
        if self._current_caller:
            parts.append(f"caller={self._current_caller}")
        logger.info(f"| 💰 {', '.join(parts)}")

    async def _call_client(
        self,
        client,
        model_config,
        messages,
        tools,
        response_format,
        stream,
        plugins,
        kwargs,
    ) -> Response:
        if model_config and model_config.model_type == "transcriptions":
            return await client(messages=messages, **kwargs)
        elif model_config and model_config.model_type == "embeddings":
            return await client(
                messages=messages,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k not in ("tools", "response_format", "stream")
                },
            )
        else:
            call_kwargs = dict(
                messages=messages,
                tools=tools,
                response_format=response_format,
                stream=stream,
                **kwargs,
            )
            if model_config and model_config.provider == "openrouter":
                call_kwargs["plugins"] = plugins
            return await client(**call_kwargs)

    async def __call__(
        self,
        name: str,
        input: Dict[str, Any],
        ctx: ModelContext = None,
        **kwargs: Any,
    ) -> Response:
        """Invoke a registered model by name.

        Args:
            name:  Registered model name (e.g. "openrouter/gemini-3-flash-preview").
            input: Call payload — keys: messages (required), tools, response_format,
                   stream, plugins, max_retries, caller.
            ctx:   Optional ModelContext (carries id, name, workspace_root, timeout, extra).
        """
        import time as _t
        import httpx

        ctx = ModelContext.from_context(ctx)
        if not ctx.name:
            ctx = ctx.model_copy(update={"name": name})

        messages = input.get("messages", [])
        tools = input.get("tools")
        response_format = input.get("response_format")
        stream = input.get("stream", False)
        plugins = input.get("plugins")
        max_retries = input.get("max_retries", 3)
        caller = input.get("caller")

        self._current_caller = caller
        # tools + response_format may be used together: the tool schemas constrain
        # tool-call arguments; response_format constrains the final answer. A turn
        # resolves to one or the other (provider serializers handle both).

        if name not in self.model_clients:
            return Response(
                type=ResponseType.LLM,
                success=False,
                message=f"Model {name} not found. Available: {list(self.models.keys())}",
            )

        model_config = self.models.get(name)
        last_exc: Exception = None

        for attempt in range(max_retries):
            _start = _t.time()
            try:
                client = await self._get_client(name)
                result = await self._call_client(
                    client,
                    model_config,
                    messages,
                    tools,
                    response_format,
                    stream,
                    plugins,
                    kwargs,
                )
                self._log_usage(name, result)
                if not result.success:
                    raise Exception(result.message or "Model returned success=False")
                is_chat = not model_config or model_config.model_type not in (
                    "transcriptions",
                    "embeddings",
                )
                if is_chat and not result.message:
                    raise Exception("Model returned empty message")
                return result
            except (
                httpx.TimeoutException,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
            ) as e:
                last_exc = e
                logger.error(
                    f"| ❌ Model {name} timed out ({_t.time()-_start:.0f}s): {e}"
                )
                break
            except Exception as e:
                last_exc = e
                _elapsed = _t.time() - _start
                tag = f", caller={self._current_caller}" if self._current_caller else ""
                if attempt < max_retries - 1:
                    logger.warning(
                        f"| ⚠️ Model {name} attempt {attempt+1}/{max_retries} failed ({_elapsed:.0f}s{tag}): {e}, retrying..."
                    )
                else:
                    logger.error(
                        f"| ❌ Model {name} failed after {max_retries} attempts ({_elapsed:.0f}s{tag}): {e}"
                    )

        if model_config and model_config.fallback_model:
            fallback = model_config.fallback_model
            logger.warning(
                f"| Primary model {name} exhausted retries, falling back to {fallback}"
            )
            if fallback not in self.model_clients:
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message=f"Primary model {name} failed and fallback {fallback} not found. Error: {last_exc}",
                )
            fallback_config = self.models.get(fallback)
            try:
                fb_client = await self._get_client(fallback)
                result = await self._call_client(
                    fb_client,
                    fallback_config,
                    messages,
                    tools,
                    response_format,
                    stream,
                    plugins,
                    kwargs,
                )
                self._log_usage(fallback, result)
                if not result.success:
                    raise Exception(result.message or "Fallback returned success=False")
                is_chat = not fallback_config or fallback_config.model_type not in (
                    "transcriptions",
                    "embeddings",
                )
                if is_chat and not result.message:
                    raise Exception("Fallback returned empty message")
                logger.info(f"| Fallback model {fallback} succeeded")
                return result
            except Exception as fallback_error:
                logger.error(
                    f"| Fallback model {fallback} also failed: {fallback_error}"
                )
                return Response(
                    type=ResponseType.LLM,
                    success=False,
                    message=f"Both {name} and fallback {fallback} failed. Primary: {last_exc}, Fallback: {fallback_error}",
                )

        return Response(type=ResponseType.LLM, success=False, message=str(last_exc))

    async def stream(
        self,
        name: str,
        input: Dict[str, Any],
        ctx: ModelContext = None,
        **kwargs: Any,
    ):
        """Stream a model invocation, yielding canonical stream events.

        Provider-agnostic: delegates to the provider client's ``stream()``, which
        normalizes its wire format into the canonical event set (see
        ``autogenesis.model.types``).

        Retry/fallback are applied ONLY before the first event is emitted: if the
        upstream fails while opening the stream (transient 5xx / timeout), we retry
        the same model up to ``max_retries`` times and then fall back to
        ``fallback_model``. Once any event has been yielded downstream we can no
        longer restart safely (it would duplicate output), so a mid-stream failure
        propagates to the caller.
        """
        import httpx
        from autogenesis.model.types import buffered_response_to_events

        ctx = ModelContext.from_context(ctx)
        messages = input.get("messages", [])
        tools = input.get("tools")
        response_format = input.get("response_format")
        max_retries = input.get("max_retries", 3)

        if name not in self.model_clients:
            raise ValueError(f"Model {name} not found. Available: {list(self.models.keys())}")

        async def _events(target: str):
            """Canonical events for one model (true stream, or buffered→events)."""
            client = await self._get_client(target)
            if hasattr(client, "stream"):
                async for ev in client.stream(
                    messages=messages, tools=tools, response_format=response_format, **kwargs
                ):
                    yield ev
            else:
                # Providers without a stream(): buffer one call, re-emit as events.
                resp = await client(
                    messages=messages, tools=tools, response_format=response_format, **kwargs
                )
                async for ev in buffered_response_to_events(resp):
                    yield ev

        model_config = self.models.get(name)

        # Ordered attempt plan: primary (retried max_retries×) then fallback (once).
        plan: List[tuple] = [(name, max_retries)]
        fb = model_config.fallback_model if model_config else None
        if fb and fb != name and fb in self.model_clients:
            plan.append((fb, 1))

        last_exc: Optional[Exception] = None
        for ci, (target, attempts) in enumerate(plan):
            for attempt in range(attempts):
                started = False
                try:
                    async for ev in _events(target):
                        started = True
                        yield ev
                    return  # stream completed cleanly
                except Exception as e:
                    last_exc = e
                    if started:
                        # Already emitted output downstream — restarting would
                        # duplicate it, so surface the error instead.
                        logger.error(
                            f"| ❌ Stream {target} failed mid-stream ({type(e).__name__}); "
                            f"cannot retry: {e}"
                        )
                        raise
                    logger.warning(
                        f"| ⚠️ Stream {target} failed before first event "
                        f"(attempt {attempt+1}/{attempts}, {type(e).__name__}): {e}"
                    )
            if ci < len(plan) - 1:
                logger.warning(
                    f"| Stream {target} exhausted retries, falling back to {plan[ci+1][0]}"
                )

        # Every candidate failed before emitting anything.
        raise last_exc if last_exc else RuntimeError(f"Stream {name} failed to start")


__all__ = ["ApiKeyPool", "ModelContextManager"]
