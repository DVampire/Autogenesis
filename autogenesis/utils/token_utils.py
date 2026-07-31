"""Token counting utilities.

Uses tiktoken directly for OpenAI-compatible models and litellm.token_counter
as a universal fallback for other providers (Anthropic, Google, etc.).
"""
from typing import Any, Dict, List, Optional, Union

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

try:
    import litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False

# Models that tiktoken can handle natively
_TIKTOKEN_PROVIDERS = {"openai", "newapi", "openrouter"}

# Fallback encoding when model is not recognized by tiktoken
_FALLBACK_ENCODING = "cl100k_base"


def _tiktoken_count(text: str, model: str) -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding(_FALLBACK_ENCODING)
    return len(enc.encode(text))


def count_tokens(
    text: str,
    model: str = "",
    provider: str = "",
) -> int:
    """Count tokens for a plain text string.

    Args:
        text: The text to tokenize.
        model: Provider-specific model ID (e.g. "gpt-4o", "claude-3-5-sonnet-20241022").
        provider: Provider slug from ModelConfig (e.g. "openai", "anthropic").

    Returns:
        Estimated token count.
    """
    if _TIKTOKEN_AVAILABLE and provider in _TIKTOKEN_PROVIDERS:
        return _tiktoken_count(text, model)

    if _LITELLM_AVAILABLE:
        try:
            return litellm.token_counter(model=model, text=text)
        except Exception:
            pass

    # Last resort: character-based estimate (~4 chars per token)
    return max(1, len(text) // 4)


def count_message_tokens(
    messages: List[Dict[str, Any]],
    model: str = "",
    provider: str = "",
) -> int:
    """Count tokens for a list of chat messages.

    Args:
        messages: List of dicts with at least a "content" key (OpenAI-style).
        model: Provider-specific model ID.
        provider: Provider slug from ModelConfig.

    Returns:
        Estimated total token count across all messages.
    """
    if _LITELLM_AVAILABLE:
        try:
            return litellm.token_counter(model=model, messages=messages)
        except Exception:
            pass

    # Fallback: sum per-message content tokens
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model=model, provider=provider)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""), model=model, provider=provider)
    return total


def truncate_text(
    text: str,
    max_tokens: int,
    model: str = "",
    provider: str = "",
    truncation_marker: str = "...[truncated]",
) -> str:
    """Truncate text so it fits within max_tokens.

    Args:
        text: Input text.
        max_tokens: Maximum allowed tokens.
        model: Provider-specific model ID.
        provider: Provider slug.
        truncation_marker: String appended when truncation occurs.

    Returns:
        Truncated text (with marker) or original text if already within limit.
    """
    if count_tokens(text, model=model, provider=provider) <= max_tokens:
        return text

    # Binary search for the right character cut point
    marker_tokens = count_tokens(truncation_marker, model=model, provider=provider)
    target = max_tokens - marker_tokens

    lo, hi = 0, len(text)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if count_tokens(text[:mid], model=model, provider=provider) <= target:
            lo = mid
        else:
            hi = mid

    return text[:lo] + truncation_marker
