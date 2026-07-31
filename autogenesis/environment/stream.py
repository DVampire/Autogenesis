"""Environment live-view stream bus.

A tiny, transport-agnostic pub/sub (mirroring ``trace_manager``'s subscriber
pattern) that carries :class:`EnvironmentView` descriptors from environments to
whatever wants to surface them — chiefly the Gateway, which republishes them to
connected browser clients.

This bus deliberately carries only the small *descriptor* of where to watch a
stream (e.g. a websockify URL), never pixel data: the heavy media stream flows
directly from the browser to that endpoint, never through this process.
"""

from __future__ import annotations

import inspect
from typing import Callable, Set

from autogenesis.environment.types import EnvironmentView
from autogenesis.logger import logger


class EnvironmentStreamBus:
    """Fan out :class:`EnvironmentView` announcements to registered subscribers."""

    def __init__(self) -> None:
        self._subscribers: Set[Callable] = set()

    def subscribe(self, callback: Callable) -> None:
        """Receive every announced view without coupling emitters to a transport."""
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable) -> None:
        self._subscribers.discard(callback)

    async def emit(self, view: EnvironmentView) -> None:
        """Announce a live view. Never raises; a failing subscriber is logged only."""
        for subscriber in tuple(self._subscribers):
            try:
                result = subscriber(view)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"| ⚠️  Environment stream subscriber failed: {exc}")


# Global bus — import this everywhere.
environment_stream = EnvironmentStreamBus()
