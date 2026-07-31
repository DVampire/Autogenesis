"""TraceManager — singleton facade for the whole trace subsystem.

Lifecycle::

    await trace_manager.initialize(log_root="output/example/log/trace")
    await trace_manager.start()          # starts the writer
    ...
    await trace_manager.emit(event)      # non-blocking async emit
    ...
    await trace_manager.stop()

Trace persists events and fans them out to subscribers; it does not serve a UI
of its own. Consumers render them: the Gateway forwards subscribed events to
the web frontend, and the ``.jsonl`` files under ``<log_root>/trace`` remain
available for offline inspection.
"""

from __future__ import annotations

import inspect
import os
from typing import Optional

from autogenesis.logger import logger
from autogenesis.queue import AsyncQueue
from autogenesis.trace.types import TraceEvent
from autogenesis.trace.writer import TraceWriter
from autogenesis.utils import Singleton


class TraceManager(metaclass=Singleton):
    """Singleton that owns the event queue and writer."""

    def __init__(self) -> None:
        self._log_root: Optional[str] = None
        self._queue: Optional[AsyncQueue[TraceEvent]] = None
        self._writer: Optional[TraceWriter] = None
        self._initialized: bool = False
        self._running: bool = False
        self._subscribers = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, log_root: Optional[str] = None) -> None:
        """Set log_root and create queue / writer.  Idempotent.

        If log_root is omitted, defaults to ``{config.log_root}/trace``.
        """
        if self._initialized:
            return
        if log_root is None:
            from autogenesis.config import config
            log_root = os.path.join(config.log_root, "trace")
        self._log_root = log_root

        self._queue = AsyncQueue[TraceEvent](maxsize=20_000)
        self._writer = TraceWriter(log_root=log_root, queue=self._queue)
        self._initialized = True
        logger.info(f"| 🔍 TraceManager initialised (log_root={log_root})")

    def rebind(self, log_root: str) -> None:
        """Re-point the trace root at ``<log_root>/trace`` for a newly bound session.

        Long-lived hosts (the Gateway) initialize this manager once, before any
        session exists; binding a session re-points it (and its writer) so each
        session's event files and index live under its own log root.
        """
        trace_root = os.path.join(log_root, "trace")
        self._log_root = trace_root
        if self._writer is not None:
            self._writer.rebind(trace_root)

    async def start(self) -> None:
        """Start the writer consumer loop."""
        if not self._initialized:
            raise RuntimeError("TraceManager.initialize() must be called first")
        if self._running:
            return

        self._writer.start()
        self._running = True

    async def stop(self) -> None:
        """Drain queue and flush the writer."""
        if not self._running:
            return
        self._running = False

        if self._writer:
            await self._writer.stop()

        logger.info("| ⏹️  TraceManager stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def emit(self, event: TraceEvent) -> None:
        """Emit a trace event.  Never blocks on the caller, never raises."""
        if not self._running or self._queue is None:
            return
        self._queue.emit(event)
        for subscriber in tuple(self._subscribers):
            try:
                result = subscriber(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"| ⚠️  Trace subscriber failed: {exc}")

    def subscribe(self, callback) -> None:
        """Receive every emitted event without coupling callers to a transport."""
        self._subscribers.add(callback)

    def unsubscribe(self, callback) -> None:
        self._subscribers.discard(callback)

    @property
    def writer(self) -> Optional[TraceWriter]:
        return self._writer


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

trace_manager = TraceManager()
