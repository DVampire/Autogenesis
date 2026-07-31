"""Priority-tier text compression — keeps the most important lines within a budget."""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple


# Tier constants (lower = higher priority, always included first)
TIER_CORE = 0           # Lines starting with "Summary:", "Current work:", "Error:" etc.
TIER_HEADER = 1         # Markdown section headers (## or ###)
TIER_BULLET = 2         # Bullet points (- or *)
TIER_DETAIL = 3         # Everything else


def _classify_line(line: str) -> int:
    stripped = line.strip()
    if not stripped:
        return TIER_DETAIL
    # Core: lines with strong signal keywords
    if re.match(r"^(Summary|Current work|Error|Warning|TODO|FIXME|File|Key):", stripped, re.I):
        return TIER_CORE
    # Section headers
    if stripped.startswith("##") or stripped.startswith("###"):
        return TIER_HEADER
    # Bullets
    if stripped.startswith(("- ", "* ", "• ")):
        return TIER_BULLET
    return TIER_DETAIL


def compress_text(
    text: str,
    max_chars: int,
    max_line_chars: int = 200,
    omission_notice: bool = True,
) -> str:
    """Compress text to fit within max_chars by greedily selecting high-priority lines.

    Lines are classified into tiers (CORE→HEADER→BULLET→DETAIL) and selected
    greedily within the budget. Duplicate lines (case-insensitive) are dropped.
    Lines longer than max_line_chars are truncated.
    """
    # Normalize whitespace within lines (not across lines)
    raw_lines = text.splitlines()
    lines: List[Tuple[int, str]] = []  # (tier, normalized_line)
    seen = set()

    for raw in raw_lines:
        # Collapse internal whitespace
        normalized = re.sub(r"[ \t]+", " ", raw).rstrip()
        key = normalized.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        # Truncate long lines
        if len(normalized) > max_line_chars:
            normalized = normalized[:max_line_chars - 1] + "…"
        lines.append((_classify_line(normalized), normalized))

    # Greedy selection by tier
    selected: List[str] = []
    omitted = 0
    used_chars = 0

    for tier in (TIER_CORE, TIER_HEADER, TIER_BULLET, TIER_DETAIL):
        tier_lines = [l for t, l in lines if t == tier]
        for line in tier_lines:
            cost = len(line) + 1  # +1 for newline
            if used_chars + cost <= max_chars:
                selected.append(line)
                used_chars += cost
            else:
                omitted += 1

    result = "\n".join(selected)
    if omitted > 0 and omission_notice:
        notice = f"\n… {omitted} additional line{'s' if omitted != 1 else ''} omitted"
        if used_chars + len(notice) <= max_chars:
            result += notice

    return result
