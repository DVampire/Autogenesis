"""Config assembly validation — a lightweight pass over the mmengine config.

Borrowed (in spirit) from HarnessX's build-time conflict detection, but kept as
a validation *pass* over the existing mmengine config rather than a parallel
builder DSL — the skeleton (config fragments + `.update()`) is unchanged.

Checks the component whitelists (`tool_names`, `agent_names`, …) for duplicate
entries, which silently shadow on registration and are almost always a merge
mistake. Returns a list of human-readable problems; the caller decides whether
to warn or raise (see ``run_meta_agent.py``).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, List

# The component whitelists an assembled config may declare.
_WHITELISTS = [
    "agent_names",
    "tool_names",
    "skill_names",
    "connector_names",
    "env_names",
    "memory_names",
    "hook_names",
    "benchmark_names",
]


def _duplicates(items: Any) -> List[str]:
    if not isinstance(items, (list, tuple)):
        return []
    names = [x for x in items if isinstance(x, str)]
    return [name for name, n in Counter(names).items() if n > 1]


def validate_assembly(config: Any, *, strict: bool = False) -> List[str]:
    """Scan the config's component whitelists for duplicate entries.

    Returns a list of problem strings (empty if clean). With ``strict=True``,
    raises ``ValueError`` when any problem is found.
    """
    problems: List[str] = []
    for key in _WHITELISTS:
        try:
            value = getattr(config, key, None)
        except Exception:
            value = None
        dups = _duplicates(value)
        if dups:
            problems.append(f"{key} has duplicate entries: {dups}")

    if problems and strict:
        raise ValueError("Config assembly validation failed:\n  - " + "\n  - ".join(problems))
    return problems


__all__ = ["validate_assembly"]
