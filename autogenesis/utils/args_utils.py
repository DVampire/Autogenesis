"""Utility functions for parsing tool arguments."""

import json
from typing import Dict, Any


def parse_tool_args(args_str: str) -> Dict[str, Any]:
    """Parse a tool-arguments JSON string into a dict, robustly.

    LLMs frequently emit JSON whose string values contain unescaped double
    quotes (e.g. a file ``content`` holding ``python -c "..."``) or that is cut
    off mid-string. Lenient parsers (``dirtyjson``) and regex fallbacks silently
    *truncate* such values at the first stray quote, which corrupts written
    files. We therefore:

      1. Try strict ``json.loads`` (fast path for well-formed input).
      2. Fall back to ``json_repair`` which repairs unescaped quotes, trailing
         commas, and truncated JSON **without dropping content**.

    Args:
        args_str: Raw JSON string from LLM output.

    Returns:
        Parsed dict, or ``{}`` if nothing dict-like could be recovered.
    """
    if not args_str:
        return {}

    # 1) Strict JSON — well-formed input parses losslessly here.
    try:
        result = json.loads(args_str)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 2) Repair malformed JSON (unescaped quotes, trailing commas, truncation).
    #    json_repair recovers the full string value instead of truncating it.
    try:
        import json_repair

        repaired = json_repair.loads(args_str)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass

    return {}
