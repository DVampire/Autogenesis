"""Kernel Manager Server

One Jupyter Server per project, and one kernel inside it that *everything* uses:
the agent's ``code_interpreter_tool``, the Science view's REPL, and JupyterLab.

That is the whole design. A raw kernel here plus a second kernel somewhere else
means two sets of variables and a synchronisation problem; one server means the
question does not arise. It also means the history below is complete — every
execution went through here, so the Science view can render what the agent ran
without anybody writing a mirror of it.

The server is a subprocess of this container, started lazily, bound to loopback
on an ephemeral port with no token: it is reachable only from here and from the
gateway's authorised proxy route.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.kernel.types import Execution, KernelOutput, KernelResult, KernelStatus
from autogenesis.logger import logger

#: Callback fired with each output as it arrives, so a long cell streams.
OnOutput = Callable[[KernelOutput], Awaitable[None]]

#: Shut a project's server down after this long with nobody near it — AND only
#: when its kernel is idle. Time alone is not enough: a training run can hold a
#: kernel for hours without anyone watching, and reaping on the clock would kill
#: it. That is exactly what the old science container's reaper did.
IDLE_TIMEOUT_SECONDS = 7200.0
#: How often the reaper looks. Cheap — one HTTP call per running server.
REAP_INTERVAL_SECONDS = 300.0

#: How many executions to remember per project. Enough to read back a session's
#: work; old entries fall off rather than growing without bound.
HISTORY_LIMIT = 500


class _Project(BaseModel):
    """One project's Jupyter Server and the kernel everything shares."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    key: str
    workspace: str
    base_url: str = ""
    port: int = 0
    kernel_id: str = ""
    session_id: str = ""
    process: Optional[object] = Field(default=None, exclude=True)
    busy: bool = False
    #: Last time anyone executed, watched or proxied through this server. What
    #: the reaper measures; refreshed by every path a live user takes.
    last_seen: float = Field(default_factory=time.time)
    history: List[Execution] = Field(default_factory=list)


class KernelManagerServer(BaseModel):
    """Start, reuse, and execute against one kernel per project."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    #: How long a single execution may run before it is interrupted.
    timeout_seconds: float = Field(default=600.0)
    #: Kernel to start. ``python3`` is the one every install has; other
    #: languages register their own kernelspec name.
    default_kernel: str = Field(default="python3")
    #: How long to wait for a freshly started server to answer.
    ready_timeout_seconds: float = Field(default=120.0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._projects: Dict[str, _Project] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._starting: Dict[str, asyncio.Lock] = {}
        self._reaper: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------- server
    def base_url(self, key: str) -> Optional[str]:
        """Where this project's Jupyter Server lives, or None if not started.

        The gateway proxies JupyterLab through this, so the browser reaches the
        Lab on the UI's own origin rather than a port of its own.
        """
        project = self._projects.get(key)
        if project is None:
            return None
        # Every proxied JupyterLab request comes through here, so an open Lab
        # keeps itself alive without depending on the panel's heartbeat.
        project.last_seen = time.time()
        return project.base_url

    def lab_path(self, key: str) -> str:
        """Sub-path the server is served under, e.g. ``/science/<project>``.

        Jupyter is started with this as ``--ServerApp.base_url``, so every
        absolute URL it emits already carries the prefix and the UI can host the
        Lab at whatever origin the browser used.
        """
        return f"/science/{key}"

    async def _ensure_server(self, key: str, workspace: Optional[str] = None) -> _Project:
        """This project's Jupyter Server, starting one if needed."""
        existing = self._projects.get(key)
        if existing is not None:
            return existing

        lock = self._starting.setdefault(key, asyncio.Lock())
        async with lock:
            existing = self._projects.get(key)
            if existing is not None:
                return existing

            root = str(workspace or config.workspace_root or os.getcwd())
            os.makedirs(root, exist_ok=True)
            port = _free_port()
            base = self.lab_path(key)
            command = [
                shutil.which("jupyter") or "jupyter", "lab",
                "--no-browser", "--allow-root",
                "--ip=127.0.0.1", f"--port={port}",
                f"--notebook-dir={root}",
                f"--ServerApp.base_url={base}/",
                "--ServerApp.token=", "--ServerApp.password=",
                "--ServerApp.disable_check_xsrf=True",
                "--ServerApp.allow_origin=*",
                # Reaped explicitly on shutdown; do not let a stray SIGHUP take
                # a running experiment with it.
                "--ServerApp.quit_button=False",
            ]
            process = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
                command, cwd=root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            project = _Project(key=key, workspace=root, port=port,
                               base_url=f"http://127.0.0.1:{port}{base}", process=process)
            if not await self._wait_ready(project):
                process.kill()
                raise RuntimeError(f"Jupyter Server for {key} did not start in time")
            self._projects[key] = project
            self._ensure_reaper()
            logger.info(f"| 🐍 Jupyter Server for {key} on 127.0.0.1:{port} ({root})")
            return project

    async def _wait_ready(self, project: _Project) -> bool:
        import aiohttp

        deadline = time.time() + self.ready_timeout_seconds
        async with aiohttp.ClientSession() as http:
            while time.time() < deadline:
                proc = project.process
                if proc is not None and proc.poll() is not None:
                    return False  # it exited; waiting longer will not help
                try:
                    async with http.get(f"{project.base_url}/api/status",
                                        timeout=aiohttp.ClientTimeout(total=3)) as response:
                        if response.status < 400:
                            return True
                except Exception:  # noqa: BLE001 — not up yet
                    pass
                await asyncio.sleep(0.5)
        return False

    async def _ensure_kernel(self, project: _Project, kernel_name: str) -> str:
        """The kernel this project shares, asking the server to start one if needed.

        A Jupyter *session* rather than a bare kernel, bound to a path, so
        opening that path in JupyterLab attaches to this very kernel instead of
        starting a second one.
        """
        if project.kernel_id:
            return project.kernel_id
        import aiohttp

        path = f"{project.key}.ipynb"
        async with aiohttp.ClientSession() as http:
            async with http.get(f"{project.base_url}/api/sessions",
                                timeout=aiohttp.ClientTimeout(total=30)) as response:
                for existing in await response.json():
                    if existing.get("path") == path and (existing.get("kernel") or {}).get("id"):
                        project.kernel_id = existing["kernel"]["id"]
                        return project.kernel_id
            payload = {"path": path, "type": "notebook", "name": path,
                       "kernel": {"name": kernel_name}}
            async with http.post(f"{project.base_url}/api/sessions", json=payload,
                                 timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Jupyter refused a kernel: {response.status} {await response.text()}")
                body = await response.json()
        project.kernel_id = body["kernel"]["id"]
        project.session_id = str(body.get("id") or project.key)
        return project.kernel_id

    # ---------------------------------------------------------------- lifecycle
    async def shutdown(self, key: str) -> bool:
        """Stop one project's server and kernel. True if one was running."""
        project = self._projects.pop(key, None)
        if project is None:
            return False
        proc = project.process
        if proc is not None:
            try:
                proc.terminate()
                for _ in range(50):
                    if proc.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.warning(f"| ⚠️ Jupyter Server {key} did not stop cleanly: {exc}")
        return True

    async def restart(self, key: str, kernel_name: Optional[str] = None) -> bool:
        """Throw the interpreter state away, keeping the server and the history."""
        project = self._projects.get(key)
        if project is None or not project.kernel_id:
            return False
        import aiohttp

        async with aiohttp.ClientSession() as http:
            async with http.post(f"{project.base_url}/api/kernels/{project.kernel_id}/restart",
                                 timeout=aiohttp.ClientTimeout(total=60)) as response:
                return response.status < 400

    async def interrupt(self, key: str) -> bool:
        """Stop whatever the kernel is doing."""
        project = self._projects.get(key)
        if project is None or not project.kernel_id:
            return False
        import aiohttp

        async with aiohttp.ClientSession() as http:
            async with http.post(f"{project.base_url}/api/kernels/{project.kernel_id}/interrupt",
                                 timeout=aiohttp.ClientTimeout(total=30)) as response:
                return response.status < 400

    async def cleanup(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
        for key in list(self._projects):
            await self.shutdown(key)

    # ------------------------------------------------------------------ reap
    def _ensure_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap_loop(), name="kernel-reaper")

    async def _reap_loop(self) -> None:
        """Close servers nobody is near — but never one still computing.

        The gateway has no "close this project", so time is what frees these.
        Time ALONE would be wrong: a training run holds a kernel for hours with
        nobody watching, and the reaper this replaces killed exactly that.
        """
        while True:
            await asyncio.sleep(REAP_INTERVAL_SECONDS)
            cutoff = time.time() - IDLE_TIMEOUT_SECONDS
            for key, project in list(self._projects.items()):
                if project.last_seen >= cutoff or project.busy:
                    continue
                if await self._kernel_is_busy(project):
                    # Something is running that we did not start — a cell from
                    # JupyterLab, most likely. Push the clock forward so it is
                    # not re-checked every interval for the life of the run.
                    project.last_seen = time.time()
                    continue
                logger.info(f"| ⏲️ Kernel for {key} idle past "
                            f"{IDLE_TIMEOUT_SECONDS:.0f}s; shutting its server down")
                await self.shutdown(key)
            # Deliberately never self-terminating. Clearing itself when the last
            # project went away raced with a new one starting: _ensure_reaper
            # could see a task that had not finished yet, decline to start
            # another, and then that one would exit — leaving none. A task
            # asleep for five minutes costs nothing; cleanup() cancels it.

    @staticmethod
    async def _kernel_is_busy(project: _Project) -> bool:
        """Ask the server, not ourselves.

        ``project.busy`` only covers executions WE issued. A cell run from an
        open JupyterLab tab is invisible to it, and reaping through one would
        lose the user's work — so the authority is the server's own
        ``execution_state``.
        """
        if not project.kernel_id:
            return False
        import aiohttp

        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(f"{project.base_url}/api/kernels/{project.kernel_id}",
                                    timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status >= 400:
                        return False
                    body = await response.json()
        except Exception as exc:  # noqa: BLE001 — unreachable is not "busy"
            logger.warning(f"| ⚠️ Could not read kernel state for {project.key}: {exc}")
            return False
        return str(body.get("execution_state") or "") == "busy"

    def running(self) -> List[str]:
        return list(self._projects)

    # ------------------------------------------------------------- inspection
    def history(self, key: str, limit: int = 200) -> List[Execution]:
        """What has run in this project's kernel, oldest first.

        Complete by construction: every execution goes through this manager, so
        the Science view renders this instead of a mirror that would drift.
        """
        project = self._projects.get(key)
        return list(project.history[-limit:]) if project else []

    def status(self, key: str) -> KernelStatus:
        project = self._projects.get(key)
        if project is None:
            return KernelStatus(running=False)
        project.last_seen = time.time()
        return KernelStatus(running=True, busy=project.busy, kernel_name=self.default_kernel,
                            executions=len(project.history), workspace=project.workspace)

    # ---------------------------------------------------------------- execute
    async def execute(self, code: str, *, key: str = "default",
                      kernel_name: Optional[str] = None,
                      workspace: Optional[str] = None,
                      language: str = "python",
                      origin: str = "agent",
                      on_output: Optional[OnOutput] = None) -> KernelResult:
        """Run ``code`` in the project's kernel and collect everything it produced.

        Serialized per project: a kernel executes one cell at a time, and two
        concurrent callers would otherwise interleave their iopub messages.
        """
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            started = datetime.now(timezone.utc)
            clock = time.time()
            try:
                project = await self._ensure_server(key, workspace)
                kernel_id = await self._ensure_kernel(project, kernel_name or self.default_kernel)
            except Exception as exc:  # noqa: BLE001 — a missing kernel is a failed result
                return KernelResult(success=False, error=f"Could not start a kernel: {exc}")

            project.busy = True
            project.last_seen = time.time()
            try:
                result = await self._run(project, kernel_id, code, on_output)
            finally:
                project.busy = False

            # An empty cell is how the server gets booted (see
            # ScienceManagerServer.start): it runs through the same path as
            # everything else, but there is nothing to show for it.
            if not code.strip():
                return result

            project.history.append(Execution(
                execution_count=result.execution_count, code=code, language=language,
                outputs=result.outputs, success=result.success, error=result.error,
                origin="user" if origin == "user" else "agent",
                started_at=started.isoformat(),
                duration_ms=int((time.time() - clock) * 1000),
            ))
            del project.history[:-HISTORY_LIMIT]
            return result

    async def _run(self, project: _Project, kernel_id: str, code: str,
                   on_output: Optional[OnOutput]) -> KernelResult:
        import aiohttp

        result = KernelResult()
        outputs: List[KernelOutput] = []
        url = f"{project.base_url}/api/kernels/{kernel_id}/channels?session_id={project.session_id}"

        try:
            async with aiohttp.ClientSession() as http:
                async with http.ws_connect(url, heartbeat=30,
                                           timeout=aiohttp.ClientTimeout(total=60)) as socket_:
                    request = _message("execute_request", {
                        "code": code, "silent": False, "store_history": True,
                        "user_expressions": {}, "allow_stdin": False, "stop_on_error": True,
                    }, project.session_id)
                    await socket_.send_json(request)
                    msg_id = request["header"]["msg_id"]
                    deadline = asyncio.get_event_loop().time() + self.timeout_seconds

                    while True:
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            await self.interrupt(project.key)
                            result.success = False
                            result.error = f"Execution exceeded {self.timeout_seconds:.0f}s and was interrupted."
                            break
                        try:
                            raw = await asyncio.wait_for(socket_.receive(), timeout=remaining)
                        except asyncio.TimeoutError:
                            continue
                        if raw.type is not aiohttp.WSMsgType.TEXT:
                            break  # the socket closed under us
                        import json

                        message = json.loads(raw.data)
                        # Messages from an earlier cell can still be draining;
                        # only this execution's replies describe this execution.
                        if (message.get("parent_header") or {}).get("msg_id") != msg_id:
                            continue
                        if message.get("channel") != "iopub":
                            continue
                        output, done = _interpret(message, result)
                        if output is not None:
                            outputs.append(output)
                            if on_output is not None:
                                await on_output(output)
                        if done:
                            break
        except Exception as exc:  # noqa: BLE001 — a dead kernel is a failed cell
            result.success = False
            result.error = f"The kernel did not answer: {exc}"

        result.outputs = outputs
        return result


def _message(msg_type: str, content: dict, session: str) -> dict:
    """One Jupyter wire message, JSON-shaped for the WebSocket channel."""
    import uuid

    return {
        "header": {"msg_id": uuid.uuid4().hex, "username": "autogenesis", "session": session,
                   "date": datetime.now(timezone.utc).isoformat(), "msg_type": msg_type,
                   "version": "5.3"},
        "parent_header": {}, "metadata": {}, "content": content, "channel": "shell",
    }


def _interpret(message: dict, result: KernelResult) -> tuple[Optional[KernelOutput], bool]:
    """Turn one iopub message into an output, and say whether the cell is done."""
    msg_type, content = message.get("msg_type"), message.get("content") or {}
    if msg_type == "stream":
        return KernelOutput(type="stream", name=content.get("name"),
                            data={"text/plain": content.get("text", "")}), False
    if msg_type == "execute_input":
        # The kernel's counter arrives here, on EVERY execution. Reading it from
        # execute_result instead left every cell that only printed or only drew
        # a figure labelled [None] — most of them.
        result.execution_count = content.get("execution_count")
        return None, False
    if msg_type in ("execute_result", "display_data", "update_display_data"):
        return KernelOutput(type="result" if msg_type == "execute_result" else "display",
                            data=dict(content.get("data") or {})), False
    if msg_type == "error":
        # nbformat's traceback is a list of lines that do NOT carry their own
        # newline, unlike stream text — joining it the other way glues the whole
        # traceback into one unreadable line.
        traceback = "\n".join(content.get("traceback") or [])
        result.success = False
        result.error = _strip_ansi(traceback) or f"{content.get('ename')}: {content.get('evalue')}"
        return KernelOutput(type="error", data={"text/plain": result.error}), False
    if msg_type == "status" and content.get("execution_state") == "idle":
        return None, True
    return None, False


def _strip_ansi(text: str) -> str:
    """Tracebacks arrive colourized; the colour codes are noise in a transcript."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")


def _free_port() -> int:
    """An ephemeral loopback port, chosen by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# Global kernel manager instance
kernel_manager = KernelManagerServer()

__all__ = ["KernelManagerServer", "kernel_manager", "HISTORY_LIMIT"]
