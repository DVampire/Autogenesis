"""MonitorAgent — procedural agent that launches a bash subprocess and polls it periodically.

Design
------
- Overrides ``on_start`` and returns ``None`` (async resolution).
- Spawns a single owned background task, ``_monitor_loop``, which:
    * Creates and owns a ``_drain_output`` task that continuously reads stdout in
      fixed-size chunks (no line-length limit) into a bounded rolling buffer.
    * Waits on a single long-lived ``process.wait()`` task; on each poll-interval
      timeout it sends a ``MonitorProgressMessage`` to the parent AgentRef inbox.
    * On completion **flushes the drain task first** so the final lines of output
      are never lost, then resolves ``ref._pending_reply`` with the captured output.
    * On ``max_wait`` exceeded kills the process and resolves the reply with a
      TimeoutError (the parent surfaces this as a failed subtask).
- ``parent_ref`` is passed as an explicit kwarg by MetaAgent._run_subtask.

Cancellation / cleanup
----------------------
- The background task is held by a strong reference (``self._bg_tasks``) so the
  event loop cannot garbage-collect it mid-flight.
- A done-callback on ``ref._pending_reply`` cancels the loop if the awaiting
  future is cancelled (e.g. ``invoke(timeout=...)`` expiry), and the loop's
  ``CancelledError``/``finally`` handlers kill the subprocess and stop draining.
- Absent any external signal, the ``max_wait`` guard bounds how long an orphaned
  subprocess can survive.

Note: the buffer is a rolling window (``_MAX_BUFFER_CHARS``), so the resolved
output is the *most recent* output, not necessarily the entire history.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque, Dict, Optional, Set

from pydantic import ConfigDict, Field, PrivateAttr

from autogenesis.protocol import protocol_manager, MonitorProgressMessage
from autogenesis.agent.types import AgentContext, AgentType, ProceduralAgent
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import AGENT
from autogenesis.utils.name_utils import make_id


@AGENT.register_module(force=True)
class MonitorAgent(ProceduralAgent):
    """Launches a bash command and monitors it, sending periodic progress reports to the parent agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="monitor_agent")
    description: str = Field(
        default=(
            "Starts a long-running bash process and monitors it, "
            "reporting progress to the parent agent at regular intervals."
        )
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = Field(default=False)
    agent_type: AgentType = Field(default=AgentType.PROCEDURAL)

    poll_interval: int = Field(default=30, description="Seconds between progress reports.")
    max_wait: int = Field(default=3600, description="Maximum seconds to wait before killing the process.")
    tail_lines: int = Field(default=50, description="Lines of recent stdout to include in each progress report.")

    # Read stdout in fixed-size chunks; bound the rolling buffer by chunk count.
    _CHUNK_SIZE: int = 4096
    _MAX_BUFFER_CHARS: int = 256_000

    # Strong references to in-flight background tasks (prevents GC; allows cleanup).
    _bg_tasks: Set[asyncio.Task] = PrivateAttr(default_factory=set)

    def __init__(
        self,
        base_dir: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        poll_interval: int = 30,
        max_wait: int = 3600,
        tail_lines: int = 50,
        enable_evolving: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            base_dir=base_dir,
            name=name,
            description=description,
            metadata=metadata,
            enable_evolving=enable_evolving,
            **kwargs,
        )
        self.poll_interval = poll_interval
        self.max_wait = max_wait
        self.tail_lines = tail_lines

    # ------------------------------------------------------------------
    # Lifecycle entry point — overrides on_start for async resolution
    # ------------------------------------------------------------------

    async def on_start(
        self,
        task: str,
        files: Optional[list],
        ctx: Optional[AgentContext],
        ref: Any,
        **kwargs: Any,
    ) -> Optional[Response]:
        """Spawn the bash subprocess and start the background monitor loop.

        Overrides the base lifecycle to resolve asynchronously: it emits a trace start
        event, launches the command, kicks off ``_monitor_loop`` (held by a strong
        reference and wired to cancel if the caller's reply future is cancelled), and
        returns ``None`` so the loop later resolves ``ref._pending_reply``. Per-invocation
        ``command``/``poll_interval``/``max_wait``/``tail_lines`` in ``kwargs`` fall back
        to the instance defaults.

        Returns:
            A failure Response if the process could not be spawned; otherwise ``None``
            (the result is delivered later via the pending reply future).
        """
        command = kwargs.get("command") or task
        parent_ref = kwargs.get("parent_ref")

        # Per-invocation overrides fall back to the instance defaults.
        poll_interval = int(kwargs.get("poll_interval") or self.poll_interval)
        max_wait = int(kwargs.get("max_wait") or self.max_wait)
        tail_lines = int(kwargs.get("tail_lines") or self.tail_lines)

        task_id = (ctx.id if ctx else None) or make_id()
        session_id = (ctx.id if ctx else None) or task_id

        logger.info(f"| 🚀 MonitorAgent [{task_id}]: starting process")
        logger.info(f"|    command: {command[:300]}")

        await self._emit_start(session_id, task_id, command)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            logger.error(f"| ❌ MonitorAgent [{task_id}]: failed to spawn process: {exc}")
            await self._emit_end(session_id, task_id, success=False, result=None,
                                 duration_ms=0.0, error=str(exc))
            return Response(type=ResponseType.AGENT, message=f"Failed to start process: {exc}", success=False)

        logger.info(f"| 🔵 MonitorAgent [{task_id}]: pid={process.pid}")

        monitor_task = asyncio.create_task(
            self._monitor_loop(
                process, task_id, session_id, ref, parent_ref,
                poll_interval, max_wait, tail_lines,
            ),
            name=f"monitor-loop-{task_id}",
        )
        # Hold a strong reference so the loop is not garbage-collected mid-flight.
        self._bg_tasks.add(monitor_task)
        monitor_task.add_done_callback(self._bg_tasks.discard)

        # If the awaiting future is cancelled (e.g. invoke timeout), tear the loop down.
        future = getattr(ref, "_pending_reply", None)
        if future is not None:
            future.add_done_callback(
                lambda f, mt=monitor_task: mt.cancel() if f.cancelled() else None
            )

        return None  # Async resolution — _monitor_loop will set ref._pending_reply

    # ------------------------------------------------------------------
    # Background helpers
    # ------------------------------------------------------------------

    async def _drain_output(
        self,
        stdout: asyncio.StreamReader,
        chunks: Deque[str],
    ) -> None:
        """Read stdout in fixed-size chunks into a bounded rolling buffer.

        Chunked reads avoid the StreamReader 64 KiB line-length limit, so a
        process emitting very long lines (progress bars, binary) cannot crash
        the drain and stall the pipe.
        """
        try:
            while True:
                data = await stdout.read(self._CHUNK_SIZE)
                if not data:
                    break
                chunks.append(data.decode(errors="replace"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"| ⚠️ MonitorAgent: stdout drain error: {exc}")

    async def _monitor_loop(
        self,
        process: asyncio.subprocess.Process,
        task_id: str,
        session_id: str,
        ref: Any,
        parent_ref: Any,
        poll_interval: int,
        max_wait: int,
        tail_lines: int,
    ) -> None:
        """Poll the running process, report progress, and resolve the reply on exit.

        The single owned background task: drains stdout into a rolling buffer, waits on
        one long-lived ``process.wait()``, and on each poll-interval timeout posts a
        progress report to the parent. On normal exit it flushes the drain (so trailing
        output is kept) and resolves the reply with the captured output; on ``max_wait``
        it kills the process and fails the reply with a ``TimeoutError``; on cancellation
        or unexpected error it kills the process and cancels/fails the reply. Trace end
        events are emitted on every terminal path, and the drain/wait tasks are always
        torn down in ``finally``.
        """
        loop = asyncio.get_running_loop()
        start = loop.time()

        maxlen = max(1, self._MAX_BUFFER_CHARS // self._CHUNK_SIZE)
        chunks: Deque[str] = deque(maxlen=maxlen)
        drain_task = asyncio.create_task(self._drain_output(process.stdout, chunks))
        wait_task = asyncio.ensure_future(process.wait())

        try:
            while True:
                elapsed = loop.time() - start
                remaining = max_wait - elapsed

                if remaining <= 0:
                    await self._terminate(process)
                    elapsed = loop.time() - start
                    logger.warning(
                        f"| ⏰ MonitorAgent [{task_id}]: timed out after {elapsed:.0f}s, process killed"
                    )
                    snapshot = self._tail(chunks, tail_lines)
                    await self._send_progress(
                        parent_ref, task_id, session_id, process.pid,
                        status="timeout", elapsed=elapsed, recent_output=snapshot,
                    )
                    _safe_set_exception(
                        ref,
                        TimeoutError(f"Process (pid={process.pid}) timed out after {max_wait}s"),
                    )
                    await self._emit_end(
                        session_id, task_id, success=False, result=snapshot,
                        duration_ms=elapsed * 1000, error="timeout",
                    )
                    return

                # Wait for process exit OR poll_interval — whichever comes first.
                # A single long-lived wait_task avoids accumulating shielded waiters.
                done, _ = await asyncio.wait(
                    {wait_task}, timeout=min(poll_interval, remaining)
                )

                if wait_task in done:
                    # --- Process finished: flush drain so trailing output is captured ---
                    await self._flush_drain(drain_task)
                    elapsed = loop.time() - start
                    output = "".join(chunks)
                    exit_code = process.returncode
                    success = exit_code == 0

                    logger.info(
                        f"| {'✅' if success else '❌'} MonitorAgent [{task_id}]: "
                        f"exited code={exit_code} elapsed={elapsed:.0f}s"
                    )

                    result = Response(type=ResponseType.AGENT, 
                        message=output[-4000:] if output else f"Process exited with code {exit_code}.",
                        success=success,
                        data={
                            "exit_code": exit_code,
                            "elapsed_seconds": round(elapsed, 1),
                            "pid": process.pid,
                        },
                    )
                    _safe_set_result(ref, result)

                    await self._send_progress(
                        parent_ref, task_id, session_id, process.pid,
                        status="completed" if success else "failed",
                        elapsed=elapsed, recent_output=output[-2000:], exit_code=exit_code,
                    )
                    await self._emit_end(
                        session_id, task_id, success=success, result=output[-4000:],
                        duration_ms=elapsed * 1000,
                        error=None if success else f"exit code {exit_code}",
                    )
                    return

                # --- Still running — send progress report ---
                elapsed = loop.time() - start
                snapshot = self._tail(chunks, tail_lines)
                logger.info(
                    f"| 📡 MonitorAgent [{task_id}]: running, "
                    f"elapsed={elapsed:.0f}s pid={process.pid}"
                )
                await self._send_progress(
                    parent_ref, task_id, session_id, process.pid,
                    status="running", elapsed=elapsed, recent_output=snapshot,
                )

        except asyncio.CancelledError:
            await self._terminate(process)
            logger.info(f"| ✋ MonitorAgent [{task_id}]: cancelled, process killed")
            _safe_cancel(ref)
            await self._emit_end(
                session_id, task_id, success=False, result=None,
                duration_ms=(loop.time() - start) * 1000, error="cancelled",
            )
            raise

        except Exception as exc:
            logger.error(f"| ❌ MonitorAgent [{task_id}]: unexpected error: {exc}", exc_info=True)
            await self._terminate(process)
            _safe_set_exception(ref, exc)
            await self._emit_end(
                session_id, task_id, success=False, result=None,
                duration_ms=(loop.time() - start) * 1000, error=str(exc),
            )

        finally:
            if not drain_task.done():
                drain_task.cancel()
            if not wait_task.done():
                wait_task.cancel()

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tail(chunks: Deque[str], tail_lines: int) -> str:
        """Return the last ``tail_lines`` lines from the rolling buffer."""
        if not chunks:
            return ""
        return "\n".join("".join(chunks).splitlines()[-tail_lines:])

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        """Kill the process if it is still running, then reap it."""
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    @staticmethod
    async def _flush_drain(drain_task: asyncio.Task) -> None:
        """Let the drain task finish reading buffered output, bounded by a short timeout."""
        try:
            await asyncio.wait_for(asyncio.shield(drain_task), timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if not drain_task.done():
                drain_task.cancel()

    async def _send_progress(
        self,
        parent_ref: Any,
        task_id: str,
        session_id: str,
        pid: int,
        status: str,
        elapsed: float,
        recent_output: str = "",
        exit_code: Optional[int] = None,
    ) -> None:
        """Post a ``MonitorProgressMessage`` to the parent agent's inbox.

        No-op when there is no ``parent_ref``. Failures to deliver are swallowed and
        logged so a broken progress channel never disrupts the monitored process.
        """
        if parent_ref is None:
            return
        try:
            await protocol_manager.report(parent_ref, MonitorProgressMessage(
                task_id=task_id, agent_name=self.name, session_id=session_id,
                pid=pid, status=status, elapsed=elapsed,
                recent_output=recent_output, exit_code=exit_code,
            ))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"| ⚠️ MonitorAgent [{task_id}]: failed to post progress: {exc}")

    async def _emit_start(self, session_id: str, task_id: str, command: str) -> None:
        """Emit an agent-start trace event for this run; tracing errors are swallowed so
        they can never break monitoring."""
        try:
            from autogenesis.trace.server import trace_manager
            from autogenesis.trace.types import agent_start_event
            await trace_manager.emit(agent_start_event(
                session_id=session_id, task_id=task_id,
                agent_name=self.name, task_content=command[:500],
            ))
        except Exception as exc:  # pragma: no cover - tracing must never break monitoring
            logger.debug(f"| trace start emit failed: {exc}")

    async def _emit_end(
        self,
        session_id: str,
        task_id: str,
        success: bool,
        result: Optional[str],
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Emit an agent-end trace event (success, result, duration, optional error) for
        this run; tracing errors are swallowed so they can never break monitoring."""
        try:
            from autogenesis.trace.server import trace_manager
            from autogenesis.trace.types import agent_end_event
            await trace_manager.emit(agent_end_event(
                session_id=session_id, task_id=task_id, agent_name=self.name,
                success=success, result=result, duration_ms=duration_ms, error=error,
            ))
        except Exception as exc:  # pragma: no cover - tracing must never break monitoring
            logger.debug(f"| trace end emit failed: {exc}")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_set_result(ref: Any, result: Any) -> None:
    """Resolve the ref's pending reply future with ``result``, ignoring it if the
    future is missing or already settled (so the resolver is safe to call once)."""
    future = getattr(ref, "_pending_reply", None)
    if future is not None and not future.done():
        future.set_result(result)


def _safe_set_exception(ref: Any, exc: BaseException) -> None:
    """Fail the ref's pending reply future with ``exc``, ignoring it if the future is
    missing or already settled."""
    future = getattr(ref, "_pending_reply", None)
    if future is not None and not future.done():
        future.set_exception(exc)


def _safe_cancel(ref: Any) -> None:
    """Cancel the ref's pending reply future if present and not yet settled."""
    future = getattr(ref, "_pending_reply", None)
    if future is not None and not future.done():
        future.cancel()
