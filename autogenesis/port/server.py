"""Central port registry.

One place that (a) names the framework's well-known default ports and (b) hands
out and records host ports, so dynamic bindings (deploy sites, the Gateway)
are de-conflicted and discoverable instead of being ad-hoc literals scattered
across the codebase.

Allocations are persisted to ``output/.runtime/ports.json`` (``P.PORTS``),
so every process and every run sees the same picture of what is bound where.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

from autogenesis.paths import P, path_manager
from autogenesis.logger import logger
from autogenesis.utils.path_utils import home_dir

# --- Well-known framework HOST service ports (single source of truth) --------
# Only host-bound, framework-level services belong here. Ports that are internal
# to a specific environment/sandbox (e.g. a browser container's CDP/VNC ports)
# belong to that environment, not this global registry — they are fixed inside
# the container and mapped to ephemeral host ports by the opensandbox proxy, so
# they never collide on the host and never go through the PortManager.
GATEWAY = 9876          # Gateway WebSocket server
OPENSANDBOX = 8080      # local opensandbox-server daemon
UI = 5173               # Vite dev server for the web UI (single-port reverse proxy)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_free(port: int, host: str = "127.0.0.1") -> bool:
    """True if ``port`` can currently be bound on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def os_free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for an unused port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


class PortManager:
    """Reserve, record, and look up host ports, persisted to ``ports.json``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Optional[str] = None
        self._registry: Dict[str, dict] = {}

    def _ensure_loaded(self) -> None:
        if self._path is not None:
            return
        self._path = str(path_manager.get(P.PORTS, create=True))
        try:
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as f:
                    self._registry = json.load(f)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"| ⚠️ Could not load port registry: {e}")
            self._registry = {}

    def _save(self) -> None:
        if not self._path:
            return
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"| ⚠️ Could not save port registry: {e}")

    def register(
        self,
        name: str,
        port: Optional[int] = None,
        *,
        preferred: Optional[int] = None,
        type: str = "host",
        override: bool = False,
    ) -> dict:
        """Register a port under ``name`` and persist it. Returns the record.

        Every port the framework uses — framework host services, dynamically
        allocated deploy ports, and an environment's own ports — registers here
        so the whole system is visible and de-conflicted in one place.

        - ``port`` given: register that exact binding (a known/fixed port, e.g.
          the Gateway's, or an environment's resolved host port). Always refreshed.
        - ``port`` omitted: allocate one — ``preferred`` if free, else an
          OS-assigned free port. Idempotent per ``name`` (reused across calls and
          runs) unless ``override`` is set.
        - ``type`` labels the entry (``host`` | ``env`` | …) for readability.
        """
        with self._lock:
            self._ensure_loaded()
            existing = self._registry.get(name)
            if port is None:
                if existing and not override and isinstance(existing.get("port"), int):
                    return existing
                port = preferred if (preferred and is_free(preferred)) else os_free_port()
            record = {
                "name": name,
                "port": port,
                "preferred": preferred if preferred is not None else port,
                "type": type,
                "pid": os.getpid(),
                "updated_at": _now(),
            }
            self._registry[name] = record
            self._save()
            logger.info(f"| 🔌 Port registered: {name} -> {port} ({type})")
            return record

    def unregister(self, name: str) -> bool:
        """Drop ``name``'s registration (its port becomes reusable). Returns whether it existed."""
        with self._lock:
            self._ensure_loaded()
            if self._registry.pop(name, None) is not None:
                self._save()
                return True
            return False

    def get(self, name: str) -> Optional[int]:
        """Return the port registered under ``name``, or None."""
        with self._lock:
            self._ensure_loaded()
            rec = self._registry.get(name)
            return rec.get("port") if rec else None

    def get_info(self, name: str) -> Optional[dict]:
        """Return the full registration record for ``name``, or None."""
        with self._lock:
            self._ensure_loaded()
            rec = self._registry.get(name)
            return dict(rec) if rec else None

    def list(self) -> Dict[str, dict]:
        """Return the whole registry (name -> record)."""
        with self._lock:
            self._ensure_loaded()
            return {name: dict(rec) for name, rec in self._registry.items()}


# Global registry — import this everywhere.
port_manager = PortManager()
