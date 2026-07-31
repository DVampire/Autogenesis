"""Crash-safe ledger of opensandbox containers started by this framework.

Peer containers (chrome-vnc, playwright, code-interpreter) outlive a crashed
or killed gateway process: nothing destroys them, and the orphans then break
every subsequent boot (observed live: leaked chrome-vnc sandboxes made each
new browser-environment start fail with "Network connectivity error", which
silently emptied the environments capability list).

The fix is a write-ahead ledger: a sandbox id is recorded right after its
container is created and forgotten on clean destroy. Whatever is still in the
ledger when a new process boots belongs to a dead run — ``reap_stale`` force-
removes those containers before the first sandbox of the new run is created.

Assumes one framework instance per tree root (the same assumption
the port registry and deploy registry already make).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List

from autogenesis.paths import P, path_manager
from autogenesis.logger import logger


class Ledger:
    """A write-ahead ledger of live sandbox container ids, persisted to the
    tree root. Reaping removes whatever a dead run left behind."""

    DOCKER_SOCKET = "/var/run/docker.sock"

    def _path(self) -> Path:
        from autogenesis.utils.path_utils import home_dir
        return path_manager.get(P.LEDGER, create=True)

    def _load(self) -> List[str]:
        try:
            data = json.loads(self._path().read_text(encoding="utf-8"))
            return [str(item) for item in data] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, ids: List[str]) -> None:
        path = self._path()
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(sorted(set(ids))), encoding="utf-8")
        os.replace(temporary, path)

    def record(self, sandbox_id: str) -> None:
        """Note a live sandbox container (call right after successful create)."""
        if not sandbox_id:
            return
        self._write([*self._load(), str(sandbox_id)])

    def forget(self, sandbox_id: str) -> None:
        """Drop a sandbox from the ledger (call after clean destroy)."""
        if not sandbox_id:
            return
        self._write([item for item in self._load() if item != str(sandbox_id)])

    def stale_ids(self) -> List[str]:
        return self._load()

    async def _remove_container(self, name: str) -> bool:
        """Force-remove one container; True when it is gone (removed or absent).

        The framework container has the Docker socket mounted but no docker CLI,
        so the Engine API over the unix socket is the primary path; the CLI is a
        fallback for host runs without a reachable socket.
        """
        if os.path.exists(self.DOCKER_SOCKET):
            import httpx
            transport = httpx.AsyncHTTPTransport(uds=self.DOCKER_SOCKET)
            async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=20.0) as client:
                response = await client.delete(f"/containers/{name}", params={"force": "true"})
                return response.status_code in (204, 404)
        process = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", name,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return True

    async def reap_stale(self) -> List[str]:
        """Force-remove containers recorded by a previous (dead) run.

        Containers are named ``sandbox-<id>`` by the opensandbox daemon. A
        missing container is not an error — the goal is simply that nothing from
        the ledger can squat on resources for the new run. Entries stay in the
        ledger when removal is impossible (e.g. no socket and no CLI) so a later
        boot can retry.
        """
        ids = self._load()
        if not ids:
            return []
        reaped: List[str] = []
        remaining: List[str] = []
        for sandbox_id in ids:
            name = sandbox_id if sandbox_id.startswith("sandbox-") else f"sandbox-{sandbox_id}"
            try:
                if await self._remove_container(name):
                    reaped.append(name)
                else:
                    remaining.append(sandbox_id)
            except Exception as exc:  # noqa: BLE001 — reaping is best-effort by design
                logger.warning(f"| ⚠️ Sandbox ledger: could not remove {name}: {exc}")
                remaining.append(sandbox_id)
        self._write(remaining)
        if reaped:
            logger.warning(f"| 🧹 Reaped {len(reaped)} stale sandbox container(s) from a previous run: {', '.join(reaped)}")
        return reaped


# One ledger per tree root (same assumption as the port/deploy registries).
ledger = Ledger()

__all__ = ["Ledger", "ledger"]
