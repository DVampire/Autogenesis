"""Per-provider model specifications.

Model catalogs live here as data, kept separate from ``ModelContextManager``
(``context.py``). Each ``<provider>_models(...)`` function takes the runtime
defaults it needs and returns the model dicts for that provider; the manager
reads these specs and performs registration (client build + one ``ModelConfig``
per entry). This keeps the (large, frequently-edited) model lists out of the
manager logic.

Each entry is a plain dict with keys like ``model_name`` / ``model_id`` /
``model_type`` / ``temperature`` / ``max_completion_tokens`` / ``max_output_tokens``
/ ``reasoning`` / ``plugins`` / ``fallback_model`` — exactly what the registration
loops in ``context.py`` consume via ``m.get(...)``.
"""
from typing import Any, Dict, List


def _r(enabled: bool = True) -> Dict[str, Any]:
    """OpenRouter-style reasoning toggle shared by several specs."""
    return {"reasoning": {"enabled": enabled}}


def openai_models(
    *,
    max_tokens: int,
    default_temperature: Any,
    default_reasoning: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """OpenAI catalog, grouped by API surface (chat / responses / transcribe / embeddings)."""
    chat_models = [
        {
            "model_name": "openai/gpt-4o",
            "model_id": "gpt-4o",
            "model_type": "chat/completions",
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openai/gpt-4.1",
        },
        {
            "model_name": "openai/gpt-4.1",
            "model_id": "gpt-4.1",
            "model_type": "chat/completions",
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openai/gpt-4o",
        },
    ]
    response_models = [
        {
            "model_name": "openai/gpt-5",
            "model_id": "gpt-5",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/o3",
        },
        {
            "model_name": "openai/gpt-5.1",
            "model_id": "gpt-5.1",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5",
        },
        {
            "model_name": "openai/o3",
            "model_id": "o3",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5.1",
        },
        {
            "model_name": "openai/o3-mini",
            "model_id": "o3-mini",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5.1",
        },
        {
            "model_name": "openai/gpt-5.2",
            "model_id": "gpt-5.1",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5",
        },
        {
            "model_name": "openai/gpt-5.3",
            "model_id": "gpt-5.3",
            "model_type": "responses",
            "reasoning": default_reasoning,
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5",
        },
        {
            "model_name": "openai/gpt-5.4",
            "model_id": "gpt-5.4",
            "model_type": "responses",
            "reasoning": {"reasoning": {"effort": "high"}},
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5",
        },
        {
            "model_name": "openai/gpt-5.4-pro",
            "model_id": "gpt-5.4-pro",
            "model_type": "responses",
            "reasoning": {"reasoning": {"effort": "high"}},
            "max_output_tokens": max_tokens,
            "fallback_model": "openai/gpt-5.4",
        },
    ]
    transcribe_models = [
        {
            "model_name": "openai/gpt-4o-transcribe",
            "model_id": "gpt-4o-transcribe",
            "model_type": "transcriptions",
            "fallback_model": "openai/gpt-4o-transcribe",
        },
    ]
    embedding_models = [
        {
            "model_name": "openai/text-embedding-3-small",
            "model_id": "text-embedding-3-small",
            "model_type": "embeddings",
            "fallback_model": "openai/text-embedding-3-large",
        },
        {
            "model_name": "openai/text-embedding-3-large",
            "model_id": "text-embedding-3-large",
            "model_type": "embeddings",
            "fallback_model": "openai/text-embedding-3-large",
        },
        {
            "model_name": "openai/text-embedding-ada-002",
            "model_id": "text-embedding-ada-002",
            "model_type": "embeddings",
            "fallback_model": "openai/text-embedding-3-large",
        },
    ]
    return {
        "chat": chat_models,
        "response": response_models,
        "transcribe": transcribe_models,
        "embedding": embedding_models,
    }


def anthropic_models(*, max_tokens, default_temperature, default_timeout, default_plugins, default_reasoning):
    """anthropic catalog.

    Register only models that support native structured output (the beta
    output_format parameter); callers request structured output on these.
    """
    chat_models = [
        # opus-4.8 and fable-5 reject `temperature` ("deprecated for this model"),
        # so they omit it and the request is sent without the parameter.
        {
            "model_name": "anthropic/claude-opus-4.8",
            "model_id": "claude-opus-4-8",
            "model_type": "chat/completions",
            "max_completion_tokens": max_tokens,
            "fallback_model": "anthropic/claude-sonnet-4.5",
        },
        {
            "model_name": "anthropic/claude-fable-5",
            "model_id": "claude-fable-5",
            "model_type": "chat/completions",
            "max_completion_tokens": max_tokens,
            "fallback_model": "anthropic/claude-sonnet-4.5",
        },
        {
            "model_name": "anthropic/claude-sonnet-4.5",
            "model_id": "claude-sonnet-4-5-20250929",
            "model_type": "chat/completions",
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "anthropic/claude-sonnet-4.5",
        },
    ]
    return {"chat": chat_models}


def openrouter_models(*, max_tokens, default_temperature, default_timeout, default_plugins, default_reasoning):
    """openrouter catalog (restored from git HEAD)."""
    chat_models = [
        # ---- OpenAI (via OpenRouter) ----
        {
            "model_name": "openrouter/gpt-5.6-sol",
            "model_id": "openai/gpt-5.6-sol",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-4o",
            "model_id": "openai/gpt-4o",
            "model_type": "chat/completions",
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-4.1",
            "model_id": "openai/gpt-4.1",
            "model_type": "chat/completions",
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5",
            "model_id": "openai/gpt-5",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.1",
            "model_id": "openai/gpt-5.1",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.2",
            "model_id": "openai/gpt-5.2",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.3",
            "model_id": "openai/gpt-5.3",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.4",
            "model_id": "openai/gpt-5.4",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.4-pro",
            "model_id": "openai/gpt-5.4-pro",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/o3",
            "model_id": "openai/o3",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": 1.0,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/o3-mini",
            "model_id": "openai/o3-mini",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": 1.0,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gpt-5.3-codex",
            "model_id": "openai/gpt-5.3-codex",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        # ---- Anthropic (via OpenRouter) ----
        {
            "model_name": "openrouter/claude-sonnet-3.5",
            "model_id": "anthropic/claude-3.5-sonnet",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-sonnet-3.7",
            "model_id": "anthropic/claude-3.7-sonnet",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-sonnet-4",
            "model_id": "anthropic/claude-sonnet-4",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-opus-4",
            "model_id": "anthropic/claude-opus-4",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-sonnet-4.5",
            "model_id": "anthropic/claude-sonnet-4.5",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-opus-4.5",
            "model_id": "anthropic/claude-opus-4.5",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-sonnet-4.6",
            "model_id": "anthropic/claude-sonnet-4.6",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-opus-4.6",
            "model_id": "anthropic/claude-opus-4.6",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            # reasoning is capped at 8k thinking tokens so long chains of
            # thought can't consume the whole max_completion_tokens budget
            # and truncate the structured-output JSON body (which produced
            # "Unterminated string" parse failures). extra_body is passed
            # straight through to OpenRouter as the top-level `reasoning`.
            "model_name": "openrouter/claude-opus-4.8",
            "model_id": "anthropic/claude-opus-4.8",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": {"max_tokens": 8000}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/claude-fable-5",
            "model_id": "anthropic/claude-fable-5",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        # ---- Google (via OpenRouter) ----
        {
            "model_name": "openrouter/gemini-2.5-flash",
            "model_id": "google/gemini-2.5-flash",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-2.5-pro",
            "model_id": "google/gemini-2.5-pro",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3-pro-preview",
            "model_id": "google/gemini-3-pro-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3.1-pro-preview",
            "model_id": "google/gemini-3.1-pro-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3-flash-preview",
            "model_id": "google/gemini-3-flash-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            # Fast, cheap flash used as the universal fallback for every
            # openrouter model above. Its own fallback points elsewhere to
            # avoid a self-loop.
            "model_name": "openrouter/gemini-3.5-flash",
            "model_id": "google/gemini-3.5-flash",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "openrouter/gemini-2.5-flash-plugins",
            "model_id": "google/gemini-2.5-flash",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "plugins": default_plugins,
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3-flash-preview-plugins",
            "model_id": "google/gemini-3-flash-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "plugins": default_plugins,
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3.1-flash-lite-preview",
            "model_id": "google/gemini-3.1-flash-lite-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3.1-flash-lite-preview-plugins",
            "model_id": "google/gemini-3.1-flash-lite-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "plugins": default_plugins,
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/gemini-3.1-pro-preview-plugins",
            "model_id": "google/gemini-3.1-pro-preview",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "plugins": default_plugins,
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        # ---- Qwen (via OpenRouter) ----
        {
            "model_name": "openrouter/qwen3-coder",
            "model_id": "qwen/qwen3-coder",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        {
            "model_name": "openrouter/qwen3-max",
            "model_id": "qwen/qwen3-max",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        # ---- DeepSeek (via OpenRouter) ----
        {
            "model_name": "openrouter/deepseek-v3.2",
            "model_id": "deepseek/deepseek-v3.2",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
        # ---- xAI (via OpenRouter) ----
        {
            "model_name": "openrouter/grok-4.1-fast",
            "model_id": "x-ai/grok-4.1-fast",
            "model_type": "chat/completions",
            "reasoning": {"reasoning": _r()},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
    ]
    return {"chat": chat_models}


def google_models(*, max_tokens, default_temperature, default_timeout, default_plugins, default_reasoning):
    """google catalog."""
    chat_models = [
        {
            "model_name": "google/gemini-2.5-flash",
            "model_id": "gemini-2.5-flash",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-2.5-pro",
            "model_id": "gemini-2.5-pro",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-3-pro-preview",
            "model_id": "gemini-3-pro-preview",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-3.1-pro-preview",
            "model_id": "gemini-3.1-pro-preview",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-3-flash-preview",
            "model_id": "gemini-3-flash-preview",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-3.1-flash-lite-preview",
            "model_id": "gemini-3.1-flash-lite-preview",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3-flash-preview",
        },
        {
            "model_name": "google/gemini-3.5-flash",
            "model_id": "gemini-3.5-flash",
            "model_type": "chat/completions",
            "reasoning": {"thinking_config": {"thinking_budget": -1, "include_thoughts": True}},
            "temperature": default_temperature,
            "max_completion_tokens": max_tokens,
            "fallback_model": "openrouter/gemini-3.5-flash",
        },
    ]
    return {"chat": chat_models}
