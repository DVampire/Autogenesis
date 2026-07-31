"""Background-style runtime for compiled dynamic workflow programs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator

from autogenesis.config import config
from autogenesis.paths import P, path_manager
from autogenesis.response import Response
from autogenesis.utils import make_id

from .types import (
    ExecutionFrame, ExecutionState, InvocationAttempt, InvocationRun,
    InvocationState, StepType, WorkflowDefinition, WorkflowRun, WorkflowState,
)

_EXPR = re.compile(r"\$\{([^{}]+)\}")


@dataclass
class _WorkflowBudget:
    """One root budget shared by every nested Workflow run."""

    max_agents: int
    max_depth: int
    agent_count: int = 0
    root_run: Optional[WorkflowRun] = None


def _now() -> str:
    """Return the current UTC time as an ISO-8601 timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class WorkflowRuntime:
    """Execute safe IR while preserving a fully inspectable execution hierarchy.

    WorkflowStep is static program text. ExecutionFrame records each dynamic expansion
    (including map items and loop rounds). InvocationRun records concrete capability
    calls and their attempts. This separation is what keeps dynamic workflows from
    collapsing back into a fixed DAG model.
    """

    RUNTIME_VERSION = "1.1.0"
    _TRANSITIONS = {
        WorkflowState.CREATED: {WorkflowState.VALIDATING},
        WorkflowState.VALIDATING: {WorkflowState.READY, WorkflowState.REJECTED},
        WorkflowState.READY: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
        WorkflowState.RUNNING: {
            WorkflowState.PAUSING, WorkflowState.CANCELLING, WorkflowState.VERIFYING,
            WorkflowState.FAILED, WorkflowState.CANCELLED,
        },
        WorkflowState.PAUSING: {
            WorkflowState.PAUSED, WorkflowState.RESUMING, WorkflowState.CANCELLING,
            WorkflowState.FAILED, WorkflowState.CANCELLED,
        },
        WorkflowState.PAUSED: {WorkflowState.RESUMING, WorkflowState.CANCELLING},
        WorkflowState.RESUMING: {
            WorkflowState.RUNNING, WorkflowState.FAILED, WorkflowState.CANCELLED,
        },
        WorkflowState.CANCELLING: {WorkflowState.CANCELLED, WorkflowState.FAILED},
        WorkflowState.VERIFYING: {WorkflowState.SUCCEEDED, WorkflowState.FAILED},
        WorkflowState.REJECTED: {WorkflowState.RESUMING},
        WorkflowState.FAILED: {WorkflowState.RESUMING},
        WorkflowState.CANCELLED: {WorkflowState.RESUMING},
        WorkflowState.SUCCEEDED: {WorkflowState.RESUMING},
    }

    def __init__(self, max_retained_runs: int = 1000) -> None:
        self._cancel: Dict[str, asyncio.Event] = {}
        self._active: Dict[str, set[asyncio.Task]] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._continue: Dict[str, asyncio.Event] = {}
        self._runs: Dict[str, WorkflowRun] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._budgets: Dict[str, _WorkflowBudget] = {}
        self.max_retained_runs = max_retained_runs

    def _new_run(self, definition, values, ctx, run_id=None) -> WorkflowRun:
        """Create and register a fresh WorkflowRun with its checkpoint path assigned.

        Args:
            definition: The compiled workflow being executed.
            values: Raw input values for the run.
            ctx: Optional execution context used to locate the checkpoint directory.
            run_id: Optional pre-allocated run id (e.g. from :meth:`start`).

        Returns:
            The newly created run in the CREATED state.
        """
        run = WorkflowRun(
            id=run_id or make_id(), workflow_name=definition.name,
            workflow_version=definition.version, runtime_version=self.RUNTIME_VERSION,
            program_hash=definition.program_hash,
            state=WorkflowState.CREATED, input=dict(values or {}), started_at=_now(),
        )
        self._runs[run.id] = run
        run.checkpoint_path = str(self._checkpoint_path(run))
        return run

    async def run(
        self, definition: WorkflowDefinition, *, input=None, ctx=None, depth=0,
        run_id=None, _run=None, _budget=None,
    ) -> WorkflowRun:
        """Validate, admit, and execute a workflow to a terminal state.

        Moves the run through VALIDATING (status, nesting depth, input schema, and
        preflight capability discovery) then READY before driving execution. A shared
        root :class:`_WorkflowBudget` bounds total Agents and nesting depth across every
        nested run. On rejection the run is checkpointed in the REJECTED state instead
        of raising.

        Args:
            definition: The compiled workflow to run.
            input: Raw input values.
            ctx: Optional execution context.
            depth: Current nesting depth (0 for a root run).
            run_id: Optional pre-allocated run id.
            _run: Internal pre-created run (used by :meth:`start`).
            _budget: Internal shared budget for nested runs; created when absent.

        Returns:
            The terminal WorkflowRun (succeeded, failed, cancelled, or rejected).
        """
        run = _run or self._new_run(definition, input, ctx, run_id)
        ctx = self._run_context(ctx, run.id, depth)
        budget = _budget or _WorkflowBudget(
            definition.max_agents, definition.max_depth, root_run=run,
        )
        self._budgets[run.id] = budget
        self._set_state(run, WorkflowState.VALIDATING)
        try:
            if definition.status.value == "deprecated":
                raise ValueError("Deprecated Workflow cannot be executed")
            if depth >= min(definition.max_depth, budget.max_depth):
                raise ValueError(
                    f"Workflow nesting exceeds max_depth={min(definition.max_depth, budget.max_depth)}"
                )
            values = self._validate_inputs(definition, input or {})
            await self._validate_capabilities(definition)
        except Exception as exc:
            self._set_state(run, WorkflowState.REJECTED)
            run.error, run.finished_at = str(exc), _now()
            self._write_checkpoint(run)
            self._tasks.pop(run.id, None)
            self._budgets.pop(run.id, None)
            return run
        run.input, run.variables = values, {"inputs": values}
        self._set_state(run, WorkflowState.READY)
        self._write_checkpoint(run)
        return await self._drive(definition, run, ctx, depth)

    async def resume(self, definition: WorkflowDefinition, checkpoint: str | Path, *, ctx=None, depth=0) -> WorkflowRun:
        """Reload a checkpointed run and continue it against the same-version program.

        Rejects checkpoints whose runtime major version, workflow identity, or executable
        program hash no longer match (pre-1.1 checkpoints without a hash are migrated).
        Incomplete frames are reset to PENDING and non-terminal invocations re-queued,
        while already-COMPLETED invocations become CACHED so finished work is not redone.

        Args:
            definition: The registered workflow the checkpoint must match.
            checkpoint: Path to the checkpoint JSON file.
            ctx: Optional execution context.
            depth: Nesting depth to resume at.

        Returns:
            The run driven to a fresh terminal state.

        Raises:
            ValueError: On an incompatible or mismatched checkpoint.
            RuntimeError: If the run is already active in this process.
        """
        path = Path(checkpoint).resolve()
        run = WorkflowRun.model_validate_json(path.read_text(encoding="utf-8"))
        if run.runtime_version.split(".", 1)[0] != self.RUNTIME_VERSION.split(".", 1)[0]:
            raise ValueError(
                f"Checkpoint runtime_version {run.runtime_version} is incompatible with {self.RUNTIME_VERSION}"
            )
        if (run.workflow_name, run.workflow_version) != (definition.name, definition.version):
            raise ValueError("Checkpoint does not match workflow name and version")
        if run.program_hash and run.program_hash != definition.program_hash:
            raise ValueError("Checkpoint executable contract does not match the registered Workflow")
        if not run.program_hash:  # migrate pre-1.1 checkpoints after legacy identity checks
            run.program_hash = definition.program_hash
        active = self._tasks.get(run.id)
        if run.id in self._cancel or (active is not None and not active.done()):
            raise RuntimeError(f"Workflow run {run.id} is already active")
        self._set_state(run, WorkflowState.RESUMING, recovery=True)
        for item in run.frames.values():
            if item.state in {ExecutionState.RUNNING, ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.RETRY_WAIT}:
                item.state = ExecutionState.PENDING
                item.error = None
        for item in run.invocations.values():
            if item.state == InvocationState.COMPLETED:
                item.state, item.cached = InvocationState.CACHED, True
            elif item.state not in {InvocationState.CACHED}:
                item.state, item.error = InvocationState.QUEUED, None
        run.error, run.finished_at, run.paused_at = None, None, None
        run.checkpoint_path = str(path)
        self._budgets[run.id] = _WorkflowBudget(
            definition.max_agents, definition.max_depth,
            agent_count=run.agent_count, root_run=run,
        )
        return await self._drive(definition, run, ctx, depth)

    async def _drive(self, definition, run, ctx, depth):
        """Run the program under cancellation, concurrency, and pause control to a terminal state.

        Sets up the per-run cancel/continue events and concurrency semaphore, executes the
        program (optionally under the workflow timeout), then transitions through VERIFYING
        to SUCCEEDED, or to CANCELLED/FAILED on error. The ``finally`` block always cancels
        active tasks, records final counters, writes the terminal checkpoint, emits the end
        event, and releases all per-run state before pruning old runs.

        Returns:
            The run in its terminal state.
        """
        cancel = asyncio.Event()
        self._cancel[run.id], self._active[run.id] = cancel, set()
        self._semaphores[run.id] = asyncio.Semaphore(definition.max_concurrency)
        continue_event = asyncio.Event()
        continue_event.set()
        self._continue[run.id] = continue_event
        self._runs[run.id] = run
        self._set_state(run, WorkflowState.RUNNING)
        await self._emit("workflow_start", run, ctx, input=run.input)
        try:
            execution = self._execute_steps(definition.program, definition, run, run.variables, ctx, depth, "root")
            if definition.timeout:
                await asyncio.wait_for(execution, definition.timeout)
            else:
                await execution
            self._set_state(run, WorkflowState.VERIFYING)
            self._write_checkpoint(run)
            run.output = self._resolve(definition.outputs, run.variables) if definition.outputs else self._public_variables(run.variables)
            self._set_state(run, WorkflowState.SUCCEEDED)
        except asyncio.CancelledError:
            self._set_state(run, WorkflowState.CANCELLED, recovery=True)
            run.error = "Workflow cancelled"
        except Exception as exc:
            self._set_state(run, WorkflowState.FAILED, recovery=True)
            run.error = str(exc)
        finally:
            await self._cancel_active(run.id)
            if depth == 0 and run.id in self._budgets:
                run.agent_count = self._budgets[run.id].agent_count
            run.finished_at = _now()
            self._write_checkpoint(run)
            await self._emit("workflow_end", run, ctx, success=run.successful, error=run.error)
            self._cancel.pop(run.id, None)
            self._active.pop(run.id, None)
            self._semaphores.pop(run.id, None)
            self._continue.pop(run.id, None)
            self._tasks.pop(run.id, None)
            self._budgets.pop(run.id, None)
            self._prune_runs()
        return run

    @staticmethod
    def _run_context(ctx, run_id: str, depth: int):
        """A top-level run executes under its own context.

        ``ctx.id`` is the scope of everything an agent accumulates — its memory,
        its token/step/time budgets, its todo list. It is *not* where anything is
        written: that comes from ``config.workspace_root``/``log_root``, which a
        bound session owns. So a run borrowing the session's context inherited
        the conversation's memory and spent its budget, and its traces were
        broadcast on the conversation's channel.

        A run is a self-contained program, so it gets its own scope and stays
        reproducible. Nested runs (``depth > 0``) keep the parent's: a
        sub-workflow is part of the same unit of work, not a new one.
        """
        if ctx is None or depth > 0 or getattr(ctx, "id", run_id) == run_id:
            return ctx
        derive = getattr(ctx, "model_copy", None)
        # ``ctx`` is duck-typed here — callers pass anything carrying what the
        # steps need. Only a real context can be re-scoped; leave the rest alone.
        return derive(update={"id": run_id}) if derive else ctx

    def start(self, definition: WorkflowDefinition, *, input=None, ctx=None, depth=0) -> str:
        """Start a workflow in the background and return a stable run id immediately."""
        run_id = make_id()
        ctx = self._run_context(ctx, run_id, depth)
        run = self._new_run(definition, input, ctx, run_id)
        task = asyncio.create_task(
            self.run(definition, input=input, ctx=ctx, depth=depth, run_id=run_id, _run=run),
            name=f"workflow-{definition.name}-{run_id}",
        )
        self._tasks[run_id] = task
        return run_id

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Return the in-memory run for an id, or None if it is unknown or pruned."""
        return self._runs.get(run_id)

    def list_runs(self, workflow_name: Optional[str] = None) -> list[WorkflowRun]:
        """List retained runs, newest first, optionally filtered by workflow name."""
        runs = list(self._runs.values())
        if workflow_name is not None:
            runs = [run for run in runs if run.workflow_name == workflow_name]
        return sorted(runs, key=lambda run: run.started_at or "", reverse=True)

    def discard_run(self, run_id: str) -> bool:
        """Forget one terminal in-memory run; its checkpoint remains on disk."""
        if run_id in self._cancel or run_id in self._tasks:
            return False
        return self._runs.pop(run_id, None) is not None

    @classmethod
    def _set_state(cls, run: WorkflowRun, state: WorkflowState, *, recovery=False) -> None:
        """Transition a run to a new state, enforcing the explicit transition table.

        Args:
            run: The run whose state is being changed.
            state: Target state; a no-op when already current.
            recovery: When True, bypass the transition table for recovery/terminal
                paths (cancellation, failure, resume).

        Raises:
            RuntimeError: On an illegal transition when ``recovery`` is False.
        """
        if run.state == state:
            return
        if not recovery and state not in cls._TRANSITIONS.get(run.state, set()):
            raise RuntimeError(f"Illegal Workflow transition: {run.state.value} -> {state.value}")
        run.state = state

    async def cleanup(self) -> None:
        """Cancel live runs and release all process-local Runtime state."""
        for run_id, event in tuple(self._cancel.items()):
            event.set()
            continuation = self._continue.get(run_id)
            if continuation is not None:
                continuation.set()
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._cancel.clear()
        self._active.clear()
        self._semaphores.clear()
        self._continue.clear()
        self._tasks.clear()
        self._budgets.clear()
        self._runs.clear()

    def _prune_runs(self) -> None:
        """Evict oldest terminal, non-active runs once retention exceeds the cap."""
        overflow = len(self._runs) - self.max_retained_runs
        if overflow <= 0:
            return
        terminal = {
            WorkflowState.REJECTED, WorkflowState.SUCCEEDED, WorkflowState.FAILED,
            WorkflowState.CANCELLED,
        }
        for run_id, run in list(self._runs.items()):
            if overflow <= 0:
                break
            if run.state in terminal and run_id not in self._tasks:
                self._runs.pop(run_id, None)
                overflow -= 1

    async def _execute_steps(self, steps, definition, run, scope, ctx, depth, prefix):
        """Execute a sequence of steps in order, threading each result into scope.

        Each step gets a unique frame key derived from ``prefix``, its output is bound
        under ``step.id`` in both the local scope and run variables, and a checkpoint is
        written after every step so progress survives interruption.

        Returns:
            The output of the last step, or None if the sequence is empty.
        """
        last = None
        for position, step in enumerate(steps):
            await self._control_point(run)
            key = f"{prefix}.{position}:{step.id}"
            last = await self._execute_step(step, definition, run, scope, ctx, depth, key)
            scope[step.id] = last
            run.variables[step.id] = last
            self._write_checkpoint(run)
        return last

    async def _execute_step(self, step, definition, run, scope, ctx, depth, key):
        """Run one static instruction inside one dynamic ExecutionFrame."""
        frame = run.frames.get(key) or ExecutionFrame(
            key=key, parent_key=self._parent_key(key), step_id=step.id,
            step_type=step.type, state=ExecutionState.READY,
            item_index=self._index_from_key(key), scope=self._safe_scope(scope),
        )
        run.frames[key] = frame
        frame.state, frame.started_at = ExecutionState.RUNNING, frame.started_at or _now()
        await self._emit(
            "workflow_frame_start", run, ctx, action_name=step.id,
            frame_key=key,
        )
        try:
            value = await self._execute_instruction(step, definition, run, scope, ctx, depth, key)
            invocation = run.invocations.get(key)
            frame.state = (
                ExecutionState.CACHED if invocation and invocation.state == InvocationState.CACHED
                else ExecutionState.SUCCEEDED
            )
            frame.output, frame.error = value, None
            return value
        except asyncio.CancelledError:
            frame.state, frame.error = ExecutionState.CANCELLED, "Cancelled"
            raise
        except Exception as exc:
            frame.state, frame.error = ExecutionState.FAILED, str(exc)
            raise
        finally:
            frame.finished_at = _now()
            await self._emit(
                "workflow_frame_end", run, ctx, action_name=step.id,
                success=frame.state in {ExecutionState.SUCCEEDED, ExecutionState.CACHED},
                error=frame.error, frame_key=key,
            )

    async def _execute_instruction(self, step, definition, run, scope, ctx, depth, key):
        """Dispatch a single static step to the handler for its control-flow type.

        Callable steps (agent/tool/skill/connector/environment/workflow) route to
        :meth:`_call`; structural steps expand into their own dynamic frames: PARALLEL
        fans out children, MAP fans out over resolved items, BRANCH selects then/else,
        LOOP iterates until/while within ``max_rounds``, REDUCE/VERIFY fan over items,
        and CHECKPOINT forces a checkpoint write.

        Returns:
            The step's output value (shape depends on the step type).

        Raises:
            ValueError: If the step type is not supported.
        """
        if step.type in {
            StepType.AGENT, StepType.TOOL, StepType.SKILL, StepType.CONNECTOR,
            StepType.ENVIRONMENT, StepType.WORKFLOW,
            StepType.DATASOURCE, StepType.PROCESS, StepType.DATA, StepType.KNOWLEDGE, StepType.BENCHMARK,
        }:
            return await self._call(step, definition, run, scope, ctx, depth, key)
        if step.type == StepType.PARALLEL:
            return await self._parallel(step.children, definition, run, scope, ctx, depth, key, step.concurrency)
        if step.type == StepType.MAP:
            items = self._as_list(self._resolve(step.items, scope))
            async def execute(item, index):
                """Run one MAP item in its own virtual frame, via the target agent or children."""
                local = {**scope, step.item_name: item, "index": index}
                item_key = f"{key}.item[{index}]"
                item_frame = self._ensure_virtual_frame(
                    run, item_key, key, step, local,
                    item_index=index,
                )
                try:
                    if step.target:
                        synthetic = step.model_copy(update={"type": StepType.AGENT, "args": {**step.args, step.item_name: "${" + step.item_name + "}"}})
                        value = await self._call(synthetic, definition, run, local, ctx, depth, item_key)
                    else:
                        value = await self._execute_steps(step.children, definition, run, local, ctx, depth, item_key)
                    item_frame.state, item_frame.output = ExecutionState.SUCCEEDED, value
                    return value
                except asyncio.CancelledError:
                    item_frame.state, item_frame.error = ExecutionState.CANCELLED, "Cancelled"
                    raise
                except Exception as exc:
                    item_frame.state, item_frame.error = ExecutionState.FAILED, str(exc)
                    raise
                finally:
                    item_frame.finished_at = _now()
            return await self._fanout(items, execute, step.concurrency or definition.max_concurrency, run.id)
        if step.type == StepType.BRANCH:
            selected = step.children if self._truth(step.condition, scope) else step.else_children
            skipped = step.else_children if selected is step.children else step.children
            self._mark_skipped(skipped, run, key)
            return await self._execute_steps(selected, definition, run, scope, ctx, depth, key)
        if step.type == StepType.LOOP:
            outputs, unchanged = [], 0
            previous = object()
            for round_number in range(step.max_rounds or 0):
                if step.condition_mode == "while" and not self._truth(step.condition, scope):
                    break
                local = {**scope, "loop": {"round": round_number + 1, "results": outputs}}
                round_key = f"{key}.round[{round_number}]"
                round_frame = self._ensure_virtual_frame(
                    run, round_key, key, step, local,
                    iteration=round_number,
                )
                try:
                    value = await self._execute_steps(step.children, definition, run, local, ctx, depth, round_key)
                    round_frame.state, round_frame.output = ExecutionState.SUCCEEDED, value
                except asyncio.CancelledError:
                    round_frame.state, round_frame.error = ExecutionState.CANCELLED, "Cancelled"
                    raise
                except Exception as exc:
                    round_frame.state, round_frame.error = ExecutionState.FAILED, str(exc)
                    raise
                finally:
                    round_frame.finished_at = _now()
                outputs.append(value)
                scope.update({k: v for k, v in local.items() if k not in {"loop"}})
                if step.condition_mode == "until" and step.condition is not None and self._truth(step.condition, scope):
                    break
                unchanged = unchanged + 1 if value == previous else 0
                if step.no_progress_limit and unchanged >= step.no_progress_limit:
                    break
                previous = value
            return outputs
        if step.type in {StepType.REDUCE, StepType.VERIFY}:
            items = self._as_list(self._resolve(step.items, scope))
            if step.type == StepType.REDUCE:
                synthetic = step.model_copy(update={"type": StepType.AGENT, "args": {**step.args, "items": items}})
                return await self._call(synthetic, definition, run, scope, ctx, depth, key)
            async def verify(item, index):
                """Judge one item with ``min_votes`` agent calls, returning the verdict(s)."""
                local = {**scope, step.item_name: item, "index": index}
                synthetic = step.model_copy(update={"type": StepType.AGENT, "args": {**step.args, step.item_name: item}})
                verdicts = await asyncio.gather(*[
                    self._call(synthetic, definition, run, local, ctx, depth, f"{key}[{index}].vote[{vote}]")
                    for vote in range(step.min_votes)
                ])
                return verdicts[0] if step.min_votes == 1 else {"item": item, "verdicts": verdicts}
            return await self._fanout(items, verify, step.concurrency or definition.max_concurrency, run.id)
        if step.type == StepType.CHECKPOINT:
            self._write_checkpoint(run)
            return {"checkpoint": run.checkpoint_path}
        raise ValueError(f"Unsupported workflow step: {step.type}")

    async def _parallel(self, steps, definition, run, scope, ctx, depth, key, concurrency):
        """Run sibling steps concurrently and merge their outputs back into scope.

        Returns:
            A dict mapping each child ``step.id`` to its output; the same bindings are
            also written into the shared scope.
        """
        async def execute(step, index):
            """Execute one parallel branch step and return its (id, output) pair."""
            local = dict(scope)
            value = await self._execute_step(
                step, definition, run, local, ctx, depth, f"{key}.branch[{index}]",
            )
            return step.id, value
        pairs = await self._fanout(steps, execute, concurrency or definition.max_concurrency, run.id)
        result = dict(pairs)
        scope.update(result)
        return result

    async def _fanout(self, items, callback, concurrency, run_id):
        """Apply ``callback`` to each item concurrently under a bounded semaphore.

        Every task is registered as active for the run (so cancellation reaches it) and
        deregistered when the batch settles.

        Args:
            items: Iterable of items to process.
            callback: Coroutine ``(item, index) -> result``.
            concurrency: Maximum simultaneous callbacks.
            run_id: Owning run id, used for control-point checks and task tracking.

        Returns:
            Results in item order (via ``asyncio.gather``).
        """
        semaphore = asyncio.Semaphore(concurrency)
        async def guarded(item, index):
            """Run one callback under the semaphore after a pause/cancel control check."""
            async with semaphore:
                await self._control_point(self._runs[run_id])
                return await callback(item, index)
        tasks = [asyncio.create_task(guarded(item, index)) for index, item in enumerate(items)]
        self._active[run_id].update(tasks)
        try:
            return await asyncio.gather(*tasks)
        finally:
            self._active[run_id].difference_update(tasks)

    async def _call(self, step, definition, run, scope, ctx, depth, key):
        """Invoke one capability as a tracked InvocationRun with caching and retries.

        Returns the cached output when a prior invocation at this key already completed
        (the resume path). Otherwise enforces the local and root Agent budgets, resolves
        args/task against scope, then runs up to ``retries + 1`` attempts under the run's
        concurrency slot and optional per-step timeout, applying exponential backoff and
        accumulating token cost. Each phase updates the invocation/attempt state machine
        and emits node start/end trace events.

        Returns:
            The normalized invocation output.

        Raises:
            RuntimeError: If the Agent budget is exceeded.
            Exception: The last attempt's error if all retries are exhausted; or
                asyncio.CancelledError on cancellation.
        """
        cached = run.invocations.get(key)
        if cached and cached.state in {InvocationState.COMPLETED, InvocationState.CACHED}:
            cached.state, cached.cached = InvocationState.CACHED, True
            return cached.output
        budget = self._budgets[run.id]
        if step.type == StepType.AGENT and (
            run.agent_count >= definition.max_agents or budget.agent_count >= budget.max_agents
        ):
            raise RuntimeError(
                f"Workflow exceeded Agent budget (local={definition.max_agents}, root={budget.max_agents})"
            )
        if step.type in {StepType.AGENT}:
            run.agent_count += 1
            budget.agent_count += 1
            if budget.root_run is not None:
                budget.root_run.agent_count = budget.agent_count
        args = self._resolve(step.args, scope)
        task_text = self._resolve(step.task, scope)
        invocation_input = {**args, **({"task": task_text} if task_text else {})}
        record = cached or InvocationRun(
            key=key, frame_key=(key if key in run.frames else self._parent_key(key) or key), capability_type=step.type,
            capability_name=step.target or "", input=invocation_input,
        )
        run.invocations[key] = record
        record.state, record.started_at = InvocationState.QUEUED, record.started_at or _now()
        await self._emit(
            "workflow_node_start", run, ctx, action_name=step.target, input=step.args,
            frame_key=record.frame_key, invocation_key=key,
        )
        for attempt in range(step.retries + 1):
            attempt_run = InvocationAttempt(number=attempt + 1, state=InvocationState.ACQUIRING_SLOT)
            record.attempts.append(attempt_run)
            try:
                await self._control_point(run)
                record.state = InvocationState.ACQUIRING_SLOT
                async with self._semaphores[run.id]:
                    await self._control_point(run)
                    record.state = attempt_run.state = InvocationState.STARTING
                    attempt_run.started_at = _now()
                    record.state = attempt_run.state = InvocationState.RUNNING
                    invocation = self._invoke(
                        step.type, step.target, task_text, args, ctx, depth, budget=budget,
                    )
                    value = (
                        await asyncio.wait_for(invocation, step.timeout)
                        if step.timeout else await invocation
                    )
                if step.type != StepType.WORKFLOW:
                    tokens = self._token_count(value)
                    record.token_cost += tokens
                    run.token_cost += tokens
                    if budget.root_run is not None and budget.root_run is not run:
                        budget.root_run.token_cost += tokens
                record.output = self._normalize(value)
                record.state, record.error = InvocationState.COMPLETED, None
                attempt_run.state, attempt_run.finished_at = InvocationState.COMPLETED, _now()
                break
            except asyncio.CancelledError:
                record.state, record.error = InvocationState.CANCELLED, "Cancelled"
                attempt_run.state, attempt_run.error, attempt_run.finished_at = InvocationState.CANCELLED, "Cancelled", _now()
                record.finished_at = _now()
                await self._emit(
                    "workflow_node_end", run, ctx, action_name=step.target, success=False,
                    error="Cancelled", frame_key=record.frame_key, invocation_key=key,
                )
                raise
            except Exception as exc:
                record.error = str(exc)
                attempt_run.error, attempt_run.finished_at = str(exc), _now()
                if attempt >= step.retries:
                    record.state = attempt_run.state = InvocationState.FAILED
                    record.finished_at = _now()
                    await self._emit(
                        "workflow_node_end", run, ctx, action_name=step.target,
                        success=False, error=str(exc), frame_key=record.frame_key,
                        invocation_key=key,
                    )
                    raise
                record.state = attempt_run.state = InvocationState.RETRYING
                frame = run.frames.get(key)
                if frame:
                    frame.state = ExecutionState.RETRY_WAIT
                delay = step.retry_delay * (step.retry_backoff ** attempt)
                if delay:
                    await asyncio.sleep(delay)
        record.finished_at = _now()
        await self._emit(
            "workflow_node_end", run, ctx, action_name=step.target, success=True,
            frame_key=record.frame_key, invocation_key=key,
        )
        return record.output

    # Canvas agent nodes mount capabilities (tools/skills/connectors/agents/
    # environments) as comma-string args; agents read the corresponding
    # per-run allowlist from ctx.extra. Lift the mount args into a derived ctx
    # so a mounted agent is scoped to exactly its selection, without mutating
    # the shared ctx (parallel siblings must not see each other's scope).
    _MOUNT_TO_ALLOWLIST = {
        "tools": "tool_allowlist",
        "skills": "skill_allowlist",
        "connectors": "connector_allowlist",
        "agents": "agent_allowlist",
        "environments": "environment_allowlist",
        "workflows": "workflow_allowlist",
    }

    def _apply_agent_mounts(self, payload, ctx):
        overrides = {}
        for arg_key, allow_key in self._MOUNT_TO_ALLOWLIST.items():
            raw = payload.pop(arg_key, None)
            if raw is None:
                continue
            names = [part.strip() for part in str(raw).split(",") if part.strip()]
            if names:
                overrides[allow_key] = names
        if not overrides:
            return ctx
        if ctx is None:
            from autogenesis.agent.types import AgentContext
            return AgentContext(extra=dict(overrides))
        derived = ctx.model_copy()
        derived.extra = {**(getattr(ctx, "extra", None) or {}), **overrides}
        return derived

    async def _invoke(self, kind, target, task, args, ctx, depth, budget=None):
        """Route a capability call to the owning manager, keeping normal permission boundaries.

        Tool/skill/connector/environment payloads are validated against the target's
        callable schema before dispatch; nested workflows recurse through the manager
        with incremented depth and the shared budget.

        Args:
            kind: The capability :class:`StepType`.
            target: Registered capability name.
            task: Optional task text folded into the payload as ``task``.
            args: Resolved argument mapping.
            ctx: Execution context passed to the manager.
            depth: Current nesting depth (nested workflows use ``depth + 1``).
            budget: Shared root budget forwarded to nested workflow runs.

        Returns:
            The manager's raw result (later normalized by :meth:`_normalize`).

        Raises:
            ValueError: If the kind is not directly callable or arguments fail schema
                validation.
        """
        payload = dict(args or {})
        if task:
            payload.setdefault("task", task)
        if kind == StepType.AGENT:
            from autogenesis.agent import agent_manager
            ctx = self._apply_agent_mounts(payload, ctx)
            return await agent_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.TOOL:
            from autogenesis.tool import tool_manager
            await self._validate_invocation_schema(await tool_manager.get_schema(target), payload, target)
            return await tool_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.SKILL:
            from autogenesis.skill import skill_manager
            await self._validate_invocation_schema(await skill_manager.get_schema(target), payload, target)
            return await skill_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.CONNECTOR:
            from autogenesis.connector import connector_manager
            action = payload.pop("action", None)
            await self._validate_invocation_schema(
                await connector_manager.get_schema(target, action=action), payload,
                f"{target}.{action}",
            )
            return await connector_manager(name=target, input={"action": action, "args": payload}, ctx=ctx)
        if kind == StepType.ENVIRONMENT:
            from autogenesis.environment import environment_manager
            action = payload.pop("action", None)
            await self._validate_invocation_schema(
                await environment_manager.get_schema(target, action=action), payload,
                f"{target}.{action}",
            )
            return await environment_manager(name=target, action=action, input=payload, ctx=ctx)
        if kind == StepType.WORKFLOW:
            from .server import workflow_manager
            return await workflow_manager.run(
                target, input=payload, ctx=ctx, depth=depth + 1, _budget=budget,
            )
        if kind == StepType.DATASOURCE:
            from autogenesis.plugins import plugin_manager
            return await plugin_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.PROCESS:
            from autogenesis.process import process_manager
            return await process_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.DATA:
            from autogenesis.data import data_manager
            return await data_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.KNOWLEDGE:
            from autogenesis.knowledge import knowledge_manager
            return await knowledge_manager(name=target, input=payload, ctx=ctx)
        if kind == StepType.BENCHMARK:
            import json as _json

            from autogenesis.benchmark import benchmark_manager
            from autogenesis.response.types import Response, ResponseType
            # Results may arrive as a list, a JSON string, or (when a `data`
            # output port is connected) the whole {records:[...]} envelope.
            results = payload.get("results")
            if isinstance(results, str) and results.strip().startswith(("[", "{")):
                try:
                    results = _json.loads(results)
                except (ValueError, TypeError):
                    results = None
            if isinstance(results, dict):
                results = results.get("records")
            if results is None:
                container = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                results = container.get("records") if isinstance(container, dict) else None
            results = results if isinstance(results, list) else []
            # Build the target benchmark on first use (startup only inits the
            # dataset-free evaluators; a heavier one is materialized on demand).
            if await benchmark_manager.get(target) is None:
                await benchmark_manager.initialize(benchmark_names=[target])
            score = await benchmark_manager(
                benchmark_name=target, results=results,
                concurrency=int(payload.get("concurrency", 10) or 10),
            )
            return Response(
                type=ResponseType.TOOL, success=True,
                message=f"{target}: avg score {score:.4f} over {len(results)} item(s).",
                data={"benchmark": target, "score": score, "count": len(results)},
            )
        raise ValueError(f"{kind.value} is not directly callable")

    @staticmethod
    async def _validate_invocation_schema(function_calling, payload, label):
        """Validate a capability payload against its declared function-call schema.

        Args:
            function_calling: The target's function-calling schema (``{"function": {...}}``).
            payload: The resolved arguments to validate.
            label: Human-readable capability label used in error messages.

        Raises:
            ValueError: If no valid schema exists or the payload violates it.
        """
        if not function_calling:
            raise ValueError(f"No callable Schema for Workflow capability: {label}")
        parameters = function_calling.get("function", {}).get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError(f"Invalid callable Schema for Workflow capability: {label}")
        errors = sorted(
            Draft202012Validator(parameters).iter_errors(payload), key=lambda item: list(item.path),
        )
        if errors:
            raise ValueError(f"Invalid arguments for Workflow capability {label}: {errors[0].message}")

    def _resolve(self, value, scope):
        """Recursively resolve ``${path}`` template references against the scope.

        Dicts and lists are resolved element-wise. A string that is exactly one
        ``${...}`` reference yields the referenced value with its native type; embedded
        references inside larger strings are substituted as text. Non-strings pass
        through unchanged.
        """
        if isinstance(value, dict):
            return {key: self._resolve(item, scope) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, scope) for item in value]
        if not isinstance(value, str):
            return value
        exact = _EXPR.fullmatch(value)
        if exact:
            return self._path(exact.group(1).strip(), scope)
        return _EXPR.sub(lambda match: str(self._path(match.group(1).strip(), scope)), value)

    def _truth(self, expression, scope):
        """Evaluate a branch/loop condition to a boolean, supporting a ``not`` prefix.

        A None expression is False; a string beginning with ``not `` negates the
        resolved reference; otherwise the resolved value's truthiness is returned.
        """
        if expression is None:
            return False
        if isinstance(expression, str):
            stripped = expression.strip()
            if stripped.startswith("not "):
                return not bool(self._resolve("${" + stripped[4:].strip("${}") + "}", scope))
        return bool(self._resolve(expression, scope))

    @staticmethod
    def _path(path, scope):
        """Traverse a dotted ``a.b.0.c`` path through dicts, list indices, and attributes.

        Returns:
            The value at the path within the scope.

        Raises:
            ValueError: If a dict segment of the path is missing.
        """
        current: Any = scope
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    raise ValueError(f"Unknown workflow reference: ${{{path}}}")
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                current = getattr(current, part)
        return current

    @staticmethod
    def _normalize(value):
        """Convert a manager result into a plain, scope-referenceable value.

        Every capability result (Response from tool/agent/skill/connector/model,
        ActionResult from environment) unwraps to the SAME canonical shape —
        ``{message, data, files}`` — so ``${step}`` / ``${step.data.x}`` work the
        same regardless of which capability produced it. A nested WorkflowRun
        unwraps to its output; other values pass through.

        Raises:
            RuntimeError: If the result failed or the nested workflow did not succeed.
        """
        from autogenesis.environment.types import ActionResult

        if isinstance(value, (Response, ActionResult)):
            if not value.success:
                raise RuntimeError(value.message)
            return {"message": value.message, "data": value.data, "files": value.files}
        if isinstance(value, WorkflowRun):
            if not value.successful:
                raise RuntimeError(value.error or "Nested workflow failed")
            return value.output
        return value

    @staticmethod
    def _token_count(value) -> int:
        """Extract a non-negative total token count from a result's ``usage``, or 0.

        Prefers ``total_tokens``/``total``, falling back to input+output token sums.
        """
        usage = getattr(value, "usage", None)
        if usage is None:
            return 0
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        if not isinstance(usage, dict):
            return 0
        total = usage.get("total_tokens") or usage.get("total")
        if total is not None:
            return max(0, int(total))
        return max(0, int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0))

    @staticmethod
    def _as_list(value):
        """Coerce a fan-out ``items`` value to a list (None becomes empty).

        Raises:
            ValueError: If the value is neither None nor a list.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Dynamic fan-out items must resolve to a list")
        return value

    @staticmethod
    def _validate_inputs(definition, values):
        """Apply input defaults and validate values against the workflow input schema.

        Undeclared top-level inputs are rejected (``additionalProperties: false``) and
        required inputs enforced.

        Returns:
            The validated input mapping with defaults filled in.

        Raises:
            ValueError: On the first schema violation, with a located message.
        """
        result = dict(values)
        for name, spec in definition.inputs.items():
            if name not in result and spec.default is not None:
                result[name] = spec.default
        properties = {
            name: dict(spec.parameter_schema or {"type": spec.type})
            for name, spec in definition.inputs.items()
        }
        schema = {
            "type": "object",
            "properties": properties,
            "required": [name for name, spec in definition.inputs.items() if spec.required],
            "additionalProperties": False,
        }
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda item: list(item.path))
        if errors:
            issue = errors[0]
            location = ".".join(str(part) for part in issue.path) or "input"
            raise ValueError(f"Invalid Workflow {location}: {issue.message}")
        return result

    async def _validate_capabilities(self, definition: WorkflowDefinition) -> None:
        """Fail before side effects when a statically named capability is unavailable."""
        from autogenesis.agent import agent_manager
        from autogenesis.benchmark import benchmark_manager
        from autogenesis.connector import connector_manager
        from autogenesis.environment import environment_manager
        from autogenesis.data import data_manager
        from autogenesis.knowledge import knowledge_manager
        from autogenesis.plugins import plugin_manager
        from autogenesis.process import process_manager
        from autogenesis.skill import skill_manager
        from autogenesis.tool import tool_manager
        from autogenesis.workflow import workflow_manager

        validated = set()

        async def check(step, trail):
            """Verify one step's target (and its children) exists, recursing into nested workflows.

            Args:
                step: The step whose capability/action to verify.
                trail: Names on the current nesting chain, used to reject recursion.

            Raises:
                ValueError: On an unknown capability/action, or an inactive/recursive
                    nested workflow.
            """
            target = step.target or ""
            if step.type in {StepType.AGENT, StepType.REDUCE, StepType.VERIFY}:
                if await agent_manager.get_info(target) is None:
                    raise ValueError(f"Unknown Workflow Agent capability: {target}")
            elif step.type == StepType.TOOL and await tool_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Tool capability: {target}")
            elif step.type == StepType.SKILL and await skill_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Skill capability: {target}")
            elif step.type == StepType.DATASOURCE and await plugin_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Datasource (plugin) capability: {target}")
            elif step.type == StepType.PROCESS and await process_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Process capability: {target}")
            elif step.type == StepType.DATA and await data_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Data operation: {target}")
            elif step.type == StepType.KNOWLEDGE and await knowledge_manager.get_info(target) is None:
                raise ValueError(f"Unknown Workflow Knowledge operation: {target}")
            elif step.type == StepType.BENCHMARK:
                if await benchmark_manager.get_info(target) is None:
                    try:  # startup inits only exact_match; materialize others on demand
                        await benchmark_manager.initialize(benchmark_names=[target])
                    except Exception:  # noqa: BLE001 — unknown/failed benchmark reported below
                        pass
                if await benchmark_manager.get_info(target) is None:
                    raise ValueError(f"Unknown Workflow Benchmark capability: {target}")
            elif step.type == StepType.CONNECTOR:
                info = await connector_manager.get_info(target)
                action = step.args.get("action")
                if info is None or (isinstance(action, str) and "${" not in action and action not in (info.actions or [])):
                    raise ValueError(f"Unknown Workflow Connector action: {target}.{action}")
            elif step.type == StepType.ENVIRONMENT:
                info = await environment_manager.get_info(target)
                action = step.args.get("action")
                actions = (getattr(info, "actions", {}) or {}) if info is not None else {}
                if info is None or (isinstance(action, str) and "${" not in action and action not in actions):
                    raise ValueError(f"Unknown Workflow Environment action: {target}.{action}")
            elif step.type == StepType.WORKFLOW:
                nested = workflow_manager.get(target)
                if nested is None or nested.status.value != "active":
                    raise ValueError(f"Unknown or inactive nested Workflow: {target}")
                if nested.name in trail:
                    chain = " -> ".join([*trail, nested.name])
                    raise ValueError(f"Recursive Workflow invocation is forbidden: {chain}")
                await validate(nested, (*trail, nested.name))
            for child in [*step.children, *step.else_children]:
                await check(child, trail)

        async def validate(current, trail):
            """Check every step of one workflow's program once, memoized by program hash."""
            if current.program_hash in validated:
                return
            for item in current.program:
                await check(item, trail)
            validated.add(current.program_hash)

        await validate(definition, (definition.name,))

    @staticmethod
    def _public_variables(values):
        """Return run variables excluding the reserved ``inputs`` binding (default output)."""
        return {key: value for key, value in values.items() if key != "inputs"}

    def cancel(self, run_id):
        """Request cancellation of a run and wake any paused coroutine so it can terminate.

        Sets the run's cancel event, moves it to CANCELLING, releases the continue event
        (so a paused run reaches its next cancel check), cancels active fan-out tasks,
        and interrupts the run task itself.

        Returns:
            True if the run was known and signalled, False otherwise.
        """
        event = self._cancel.get(run_id)
        if event is None:
            return False
        run = self._runs.get(run_id)
        if run:
            self._set_state(run, WorkflowState.CANCELLING, recovery=True)
        event.set()
        # A paused coroutine is waiting on the continue event, so wake it to let the
        # next control-point cancellation check terminate the run.
        continue_event = self._continue.get(run_id)
        if continue_event is not None:
            continue_event.set()
        for task in self._active.get(run_id, set()):
            task.cancel()
        # Interrupt the step that is currently in flight. The cancel event alone is
        # only observed at a control point (between steps), so a run blocked inside a
        # long step — an agent's model call — would keep running, and a single-step
        # flow would reach SUCCEEDED without ever passing another control point.
        # Cancelling the run task raises CancelledError inside run(), which converts
        # it to CANCELLED and still runs the terminal/cleanup path in its `finally`.
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    def pause(self, run_id: str) -> bool:
        """Request a cooperative pause at the next safe instruction boundary."""
        event = self._continue.get(run_id)
        run = self._runs.get(run_id)
        if event is None or run is None or run.state != WorkflowState.RUNNING:
            return False
        self._set_state(run, WorkflowState.PAUSING)
        event.clear()
        return True

    def continue_run(self, run_id: str) -> bool:
        """Continue an in-memory paused run without rebuilding completed work."""
        event = self._continue.get(run_id)
        run = self._runs.get(run_id)
        if event is None or run is None or run.state not in {WorkflowState.PAUSED, WorkflowState.PAUSING}:
            return False
        self._set_state(run, WorkflowState.RESUMING)
        event.set()
        return True

    async def _control_point(self, run: WorkflowRun) -> None:
        """Cooperative pause/cancel boundary; active manager calls finish atomically."""
        if self._cancel[run.id].is_set():
            raise asyncio.CancelledError
        event = self._continue[run.id]
        if not event.is_set():
            self._set_state(run, WorkflowState.PAUSED)
            run.paused_at = _now()
            self._write_checkpoint(run)
            await event.wait()
            if self._cancel[run.id].is_set():
                raise asyncio.CancelledError
            self._set_state(run, WorkflowState.RUNNING)
            run.paused_at = None
        elif run.state == WorkflowState.RESUMING:
            self._set_state(run, WorkflowState.RUNNING)

    async def _cancel_active(self, run_id):
        """Cancel and await all outstanding fan-out tasks tracked for a run."""
        tasks = list(self._active.get(run_id, set()))
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _parent_key(key: str) -> Optional[str]:
        """Return the parent frame key, or None at the ``root`` level."""
        if "." not in key:
            return None
        parent = key.rsplit(".", 1)[0]
        return None if parent == "root" else parent

    @staticmethod
    def _index_from_key(key: str) -> Optional[int]:
        """Extract the last ``[n]`` index from a frame key (map/loop/branch), or None."""
        match = re.search(r"\[(\d+)\](?!.*\[)", key)
        return int(match.group(1)) if match else None

    @staticmethod
    def _safe_scope(scope: Dict[str, Any]) -> Dict[str, Any]:
        """Keep useful local bindings without duplicating every global result per frame."""
        return {
            key: value for key, value in scope.items()
            if key in {"item", "index", "loop"} or not isinstance(value, (dict, list))
        }

    @staticmethod
    def _ensure_virtual_frame(
        run, key, parent_key, step, scope, *, item_index=None, iteration=None,
    ) -> ExecutionFrame:
        """Get or create the ExecutionFrame for a dynamic expansion (map item/loop round).

        Reuses an existing frame on resume; otherwise creates one in RUNNING state so the
        expansion is recorded in the inspectable hierarchy.

        Returns:
            The frame registered under ``key``.
        """
        frame = run.frames.get(key) or ExecutionFrame(
            key=key, parent_key=parent_key, step_id=step.id, step_type=step.type,
            state=ExecutionState.RUNNING, item_index=item_index, iteration=iteration,
            scope=WorkflowRuntime._safe_scope(scope), started_at=_now(),
        )
        run.frames[key] = frame
        return frame

    @staticmethod
    def _mark_skipped(steps, run, parent_key):
        """Materialize non-selected branch instructions for honest trace/status views."""
        for index, step in enumerate(steps):
            key = f"{parent_key}.skipped[{index}]:{step.id}"
            run.frames[key] = ExecutionFrame(
                key=key, parent_key=parent_key, step_id=step.id, step_type=step.type,
                state=ExecutionState.SKIPPED, finished_at=_now(),
            )

    @staticmethod
    def _checkpoint_path(run):
        """Compute (and create) the per-run checkpoint file path.

        Kept in the layout rather than under the workspace: run ids are unique,
        so nothing is gained by nesting these per workspace, and writing them
        there dropped framework bookkeeping into the agent's own files — or,
        when no workspace was configured, into the current directory, outside
        ``output/`` entirely.

        Returns:
            ``output/.runtime/checkpoints/<run_id>.json``.
        """
        return path_manager.get(P.CHECKPOINTS, create=True) / f"{run.id}.json"

    @staticmethod
    def _write_checkpoint(run):
        """Atomically persist the run's full state to its checkpoint file (temp + replace).

        No-op when the run has no checkpoint path (e.g. ephemeral runs).
        """
        if not run.checkpoint_path:
            return
        path = Path(run.checkpoint_path)
        fd, temporary = tempfile.mkstemp(prefix=f".{run.id}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(run.model_dump(mode="json"), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    async def _emit(
        event_type, run, ctx, *, action_name=None, input=None, success=None,
        error=None, frame_key=None, invocation_key=None,
    ):
        """Emit a workflow trace event, swallowing errors so observability never breaks execution."""
        from autogenesis.trace import trace_manager
        from autogenesis.trace.types import TraceEvent, TraceEventType
        try:
            await trace_manager.emit(TraceEvent(
                event_type=TraceEventType(event_type), session_id=getattr(ctx, "session_id", None),
                task_id=run.id, action_type="workflow", action_name=action_name or run.workflow_name,
                label=action_name or run.workflow_name, input=input, success=success, error=error,
                metadata={
                    "workflow": run.workflow_name, "runtime_version": run.runtime_version,
                    "program_hash": run.program_hash, "token_cost": run.token_cost,
                    "frame_key": frame_key, "invocation_key": invocation_key,
                },
            ))
        except Exception:
            # Observability must never alter Workflow correctness or prevent cleanup.
            return


workflow_runtime = WorkflowRuntime()

__all__ = ["WorkflowRuntime", "workflow_runtime"]
