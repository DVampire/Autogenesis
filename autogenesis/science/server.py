"""Science manager: the workstation half of a project.

There is no science container. Everything runs in the base environment, where
the agent already runs — the agent's ``code_interpreter_tool``, the Science
view's REPL, and JupyterLab all go through the one Jupyter Server that
:mod:`autogenesis.kernel` holds open per project.

That is the whole reason the container went away. A peer container gave
isolation that was already thin (``bash_tool`` runs here as root) while costing
a second kernel the agent's variables never reached, a routing decision for
every execution, and a reaper that could kill a training run. With one
environment none of those exist, and the panel showing "what ran" is simply the
kernel's own history.

What is left here is the workstation's *furniture*: the notebooks in the
project, and what the machine is running on.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from autogenesis.kernel import kernel_manager
from autogenesis.logger import logger
from autogenesis.paths import P, path_manager
from autogenesis.science.types import ComputeStatus, Notebook


def base_path(session_id: str) -> str:
    """Sub-path this project's JupyterLab is served under, on the UI's own origin.

    Jupyter is started with this as ``--ServerApp.base_url``, so every absolute
    URL it emits already carries the prefix and the UI can host the Lab at
    whatever address the browser reached the UI at. A per-session hostname is
    resolved by the BROWSER, so it only ever works when the browser runs on the
    server itself — the same fix the Code view needed.
    """
    return kernel_manager.lab_path(session_id)


#: How often the background sampler re-reads the GPUs.
GPU_SAMPLE_SECONDS = 10.0
#: Stop sampling once nobody has asked this long — an idle gateway should not
#: keep a subprocess running every ten seconds forever.
GPU_IDLE_SECONDS = 120.0


class ScienceManagerServer:
    """The project's notebooks, and the machine they run on."""

    def __init__(self) -> None:
        #: Latest GPU reading, refreshed by a background sampler rather than by
        #: whoever happens to ask. nvidia-smi takes ~0.5s on a loaded machine:
        #: reading it inside the request made every poll wait for it, and two
        #: open tabs paid for it twice.
        self._gpus: List[dict] = []
        self._gpus_wanted_at: float = 0.0
        self._sampler: Optional[asyncio.Task] = None

    async def _sample_gpus(self) -> None:
        """Refresh the GPU reading until nobody has looked for a while."""
        while time.time() - self._gpus_wanted_at < GPU_IDLE_SECONDS:
            # In a thread, so the half second nvidia-smi takes is not half a
            # second in which the gateway cannot stream the agent's reply.
            self._gpus = await asyncio.to_thread(_gpu_status)
            await asyncio.sleep(GPU_SAMPLE_SECONDS)
        self._sampler = None

    async def gpus(self) -> List[dict]:
        """The most recent GPU reading, taken without waiting for one."""
        self._gpus_wanted_at = time.time()
        if self._sampler is None or self._sampler.done():
            # The very first caller waits for one sample; after that the panel
            # is answered from the cache and the sampler keeps it fresh.
            self._gpus = await asyncio.to_thread(_gpu_status)
            self._sampler = asyncio.create_task(self._sample_gpus(), name="gpu-sampler")
        return self._gpus

    async def start(self, session_id: str, *, workspace_root: str | Path,
                    owner: str = "local") -> dict:
        """Make sure this project's Jupyter Server is up, and say where it is.

        Starting it is the kernel manager's job — the same call the agent's
        first ``code_interpreter_tool`` would make — so opening the Science view
        and the agent running a cell converge on one server either way round.
        """
        workspace = Path(workspace_root).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        path_manager.get(P.SESSION_NOTEBOOKS, owner=owner, session_id=session_id, create=True)
        # An empty cell rather than a bespoke "start" call: it takes the same
        # path every other execution takes, so there is one way a server comes
        # up and one place it can go wrong.
        await kernel_manager.execute("", key=session_id, workspace=str(workspace), origin="user")
        logger.info(f"| 🔬 Science workstation ready for {session_id} ({workspace})")
        return self.status(session_id)

    async def stop(self, session_id: str) -> bool:
        """Shut this project's Jupyter Server down. True if one was running."""
        return await kernel_manager.shutdown(session_id)

    async def stop_all(self) -> None:
        if self._sampler is not None:
            self._sampler.cancel()
            self._sampler = None
        await kernel_manager.cleanup()

    @staticmethod
    def touch(session_id: str) -> bool:
        return session_id in kernel_manager.running()

    def upstream(self, session_id: str) -> Optional[str]:
        """Proxy target for this project's JupyterLab, or None if not started."""
        base = kernel_manager.base_url(session_id)
        # base_url already carries the /science/<id> prefix; the proxy forwards
        # the browser's path verbatim, so it needs the origin without it.
        return base.removesuffix(base_path(session_id)) if base else None

    @staticmethod
    def status(session_id: str) -> dict:
        kernel = kernel_manager.status(session_id)
        return {
            "session_id": session_id,
            "running": kernel.running,
            # Where the UI embeds the Lab, relative to its own origin, so it
            # works over any tunnel without a hostname of its own.
            "path": base_path(session_id),
            "busy": kernel.busy,
            "executions": kernel.executions,
            "workspace_root": kernel.workspace,
        }

    # ------------------------------------------------------------- compute
    async def compute(self, session_id: str) -> ComputeStatus:
        """What this machine is running on.

        The base environment's own resources — the whole host, not a slice of
        it, because that is what the agent and the kernel actually get.
        """
        kernel = kernel_manager.status(session_id)
        gpus = await self.gpus()
        total = used = free = None
        try:
            meminfo = dict(
                line.split(":", 1) for line in
                Path("/proc/meminfo").read_text(encoding="utf-8").strip().splitlines())
            total = int(meminfo["MemTotal"].split()[0]) // 1024
            used = total - int(meminfo["MemAvailable"].split()[0]) // 1024
        except (OSError, KeyError, ValueError, IndexError):
            logger.warning("| ⚠️ Could not read /proc/meminfo")
        try:
            free = shutil.disk_usage(kernel.workspace or "/").free // (1024 * 1024)
        except OSError:
            pass

        return ComputeStatus(
            running=kernel.running, busy=kernel.busy, gpus=gpus,
            cpu_count=os.cpu_count(), memory_total_mb=total, memory_used_mb=used,
            disk_free_mb=free, executions=kernel.executions,
        )

    # ----------------------------------------------------------- notebooks
    @staticmethod
    def notebooks(session_id: str, *, owner: str = "local") -> List[Notebook]:
        """Every ``.ipynb`` in the project's workspace, newest first."""
        workspace = path_manager.get(P.SESSION_WORKSPACE, owner=owner, session_id=session_id)
        if not workspace.is_dir():
            return []
        found: List[Notebook] = []
        for path in workspace.rglob("*.ipynb"):
            if ".ipynb_checkpoints" in path.parts:
                continue
            try:
                stat = path.stat()
                cells = len(json.loads(path.read_text(encoding="utf-8")).get("cells", []))
            except (OSError, ValueError):
                continue  # unreadable or mid-write; it will appear next refresh
            found.append(Notebook(
                path=str(path.relative_to(workspace)), title=path.stem,
                size_bytes=stat.st_size, cell_count=cells,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            ))
        return sorted(found, key=lambda item: item.modified_at, reverse=True)

    @staticmethod
    def save_history_as_notebook(session_id: str, name: str, *, owner: str = "local") -> Notebook:
        """Write what has run in this project's kernel out as a real ``.ipynb``.

        The panel is the kernel's live history, not a document; this is how you
        keep a copy — openable in JupyterLab, in the Code view, or by anything
        else that reads notebooks.
        """
        directory = path_manager.get(P.SESSION_NOTEBOOKS, owner=owner, session_id=session_id, create=True)
        stem = "".join(c for c in (name or "session") if c.isalnum() or c in " -_").strip() or "session"
        path = directory / f"{stem}.ipynb"
        counter = 2
        while path.exists():
            path = directory / f"{stem}-{counter}.ipynb"
            counter += 1

        cells = [{
            "cell_type": "code", "id": f"c{index}",
            "source": entry.code,
            "execution_count": entry.execution_count,
            "metadata": {"autogenesis": {"origin": entry.origin, "started_at": entry.started_at}},
            "outputs": [_to_nbformat(output) for output in entry.outputs],
        } for index, entry in enumerate(kernel_manager.history(session_id, limit=1000))]

        path.write_text(json.dumps({
            "cells": cells, "nbformat": 4, "nbformat_minor": 5, "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            },
        }, indent=1), encoding="utf-8")
        workspace = path_manager.get(P.SESSION_WORKSPACE, owner=owner, session_id=session_id)
        return Notebook(path=str(path.relative_to(workspace)), title=path.stem,
                        size_bytes=path.stat().st_size, cell_count=len(cells),
                        modified_at=datetime.now(timezone.utc).isoformat())


def _to_nbformat(output) -> dict:
    """One KernelOutput as nbformat, so the saved file is a valid notebook."""
    data = dict(output.data or {})
    if output.type == "stream":
        return {"output_type": "stream", "name": output.name or "stdout",
                "text": data.get("text/plain", "")}
    if output.type == "error":
        text = data.get("text/plain", "")
        # nbformat requires all three; only the traceback was carried, so the
        # name and value are derived from its last line rather than invented.
        last = text.strip().splitlines()[-1] if text.strip() else "Error"
        ename, _, evalue = last.partition(":")
        return {"output_type": "error", "ename": ename.strip() or "Error",
                "evalue": evalue.strip(), "traceback": text.splitlines()}
    if output.type == "result":
        return {"output_type": "execute_result", "data": data, "metadata": {}, "execution_count": None}
    return {"output_type": "display_data", "data": data, "metadata": {}}


def _gpu_status() -> List[dict]:
    """What nvidia-smi reports, or an empty list on a machine without GPUs.

    Empty is not an error — plenty of hosts have no NVIDIA card — so the panel
    says "no GPU detected" rather than showing a broken meter.
    """
    import subprocess

    binary = shutil.which("nvidia-smi")
    if not binary:
        return []
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            [binary, "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"| ⚠️ nvidia-smi did not answer: {exc}")
        return []
    if completed.returncode != 0:
        return []
    gpus: List[dict] = []
    for line in completed.stdout.strip().splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 5 or not fields[0].isdigit():
            continue
        gpus.append({
            "index": int(fields[0]), "name": fields[1],
            "memory_used_mb": int(fields[2]), "memory_total_mb": int(fields[3]),
            "utilization_percent": int(fields[4]),
        })
    return gpus


# Global science manager instance
science_manager = ScienceManagerServer()

__all__ = ["ScienceManagerServer", "science_manager", "base_path"]
