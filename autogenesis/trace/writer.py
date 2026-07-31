"""TraceWriter — async consumer that persists TraceEvents to JSON files.

One file per session: <log_root>/<session_id>.jsonl
Events are appended as newline-delimited JSON (JSONL) for streaming reads
without loading the entire file into memory.

A separate index file <log_root>/index.json maps session_id → file path
and summary metadata for the UI's session list endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from autogenesis.logger import logger
from autogenesis.queue import AsyncQueue
from autogenesis.trace.types import TraceEvent


class TraceWriter:
    """Drains an AsyncQueue[TraceEvent] and writes events to JSONL files, one per session."""

    def __init__(self, log_root: str, queue: AsyncQueue[TraceEvent]) -> None:
        self._log_root = log_root
        self._queue = queue

        # session_id → open file handle for fast append
        self._handles: Dict[str, object] = {}
        # session_id → summary dict for the index
        self._session_meta: Dict[str, Dict] = {}

        self._index_path = os.path.join(log_root, "index.json")
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def rebind(self, log_root: str) -> None:
        """Point the writer at a new trace root (called when a session is bound).

        Open handles are closed so subsequent events are appended under the new
        root, and the index follows it — each session keeps its own index.
        """
        if log_root == self._log_root:
            return
        self._close_all_handles()
        self._log_root = log_root
        self._index_path = os.path.join(log_root, "index.json")
        self._session_meta.clear()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="trace-writer")

    async def stop(self) -> None:
        await self._queue.stop()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._close_all_handles()
        await self._flush_index()

    # ------------------------------------------------------------------
    # Consumer loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        # Do not eagerly create the global trace root — per-session event files and
        # the index create their own dirs lazily, so no empty tag-level dir appears
        # for gateways that route every session to its own log root.
        await self._load_index()

        while True:
            event = await self._queue.get()
            if event is None:
                break
            try:
                await self._write_event(event)
            except Exception as e:
                logger.warning(f"| ⚠️  TraceWriter error: {e}")
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def _write_event(self, event: TraceEvent) -> None:
        session_id = event.session_id or "no_session"
        fh = self._get_handle(session_id)

        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        fh.write(line)  # type: ignore[attr-defined]
        fh.flush()      # type: ignore[attr-defined]

        # Update session metadata
        meta = self._session_meta.setdefault(session_id, {
            "session_id": session_id,
            "file": self._session_path(session_id),
            "event_count": 0,
            "first_event_at": event.timestamp.isoformat(),
            "last_event_at": event.timestamp.isoformat(),
            "agent_names": [],
            "task_ids": [],
        })
        meta["event_count"] += 1
        meta["last_event_at"] = event.timestamp.isoformat()
        if event.agent_name and event.agent_name not in meta["agent_names"]:
            meta["agent_names"].append(event.agent_name)
        if event.task_id and event.task_id not in meta["task_ids"]:
            meta["task_ids"].append(event.task_id)

        # Flush index every 50 events to avoid hammering disk
        if meta["event_count"] % 50 == 0:
            await self._flush_index()

    def _session_path(self, session_id: str) -> str:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return os.path.join(self._log_root, f"{safe}.jsonl")

    def _get_handle(self, session_id: str):
        if session_id not in self._handles:
            path = self._session_path(session_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._handles[session_id] = open(path, "a", encoding="utf-8", buffering=1)
        return self._handles[session_id]

    def _close_all_handles(self) -> None:
        for fh in self._handles.values():
            try:
                fh.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._handles.clear()

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    async def _flush_index(self) -> None:
        try:
            data = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "sessions": list(self._session_meta.values()),
            }
            os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
            tmp = self._index_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._index_path)
        except Exception as e:
            logger.warning(f"| ⚠️  TraceWriter index flush failed: {e}")

    async def _load_index(self) -> None:
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for s in data.get("sessions", []):
                self._session_meta[s["session_id"]] = s
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Read-back helpers (used by API endpoints)
    # ------------------------------------------------------------------

    def list_sessions(self) -> list:
        return list(self._session_meta.values())

    def read_session(self, session_id: str) -> list:
        """Return all events for a session as a list of dicts."""
        path = self._session_path(session_id)
        if not os.path.exists(path):
            return []
        events = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events
