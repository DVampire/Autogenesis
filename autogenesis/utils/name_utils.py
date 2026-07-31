"""Unique ID generation for the multi-agent system."""

from __future__ import annotations

import uuid

def make_id() -> str:
    """Generate an 8-character random ID."""
    return uuid.uuid4().hex[:8].lower()
