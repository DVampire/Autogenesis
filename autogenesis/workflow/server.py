"""Thin Workflow manager facade plus runtime control."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.utils import assemble_workspace_path

from .compiler import workflow_compiler
from .context import WorkflowContextManager
from .runtime import workflow_runtime
from .types import WorkflowDefinition, WorkflowEvaluation, WorkflowRun, WorkflowStatus


class WorkflowManagerServer(BaseModel):
    """Stable public API delegating registry context and runtime execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="Base directory for Workflow context data")
    workflow_context_manager: Optional[WorkflowContextManager] = Field(default=None, exclude=True)

    def __init__(self, base_dir: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.base_dir = base_dir

    def _ensure_context_manager(self) -> WorkflowContextManager:
        """Lazily create the Context so registry APIs also work before initialize()."""
        if self.workflow_context_manager is None:
            self.workflow_context_manager = WorkflowContextManager(base_dir=self.base_dir)
        return self.workflow_context_manager

    async def initialize(self, workflow_names: Optional[List[str]] = None) -> None:
        """Create the registry context and load built-in workflows (optionally filtered)."""
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "workflow"))
        self.workflow_context_manager = WorkflowContextManager(base_dir=self.base_dir)
        await self._ensure_context_manager().initialize(workflow_names=workflow_names)
        logger.info("| ✅ Workflow manager Server initialized")

    async def cleanup(self) -> None:
        """Tear down the runtime (cancelling live runs) and the registry context."""
        await workflow_runtime.cleanup()
        await self._ensure_context_manager().cleanup()

    # Registry/context facade — signatures remain compatible with the previous manager.
    def register(self, workflow: WorkflowDefinition | str | Path, *, override=False, status=None):
        """Compile (if needed) and register a workflow via the context; see Context.register."""
        return self._ensure_context_manager().register(workflow, override=override, status=status)

    def unregister(self, name: str) -> bool:
        """Remove a registered workflow; returns True if one was present."""
        return self._ensure_context_manager().unregister(name)

    def restore(self, name: str, version: str) -> Optional[WorkflowDefinition]:
        """Restore a previously registered historical version as active."""
        return self._ensure_context_manager().restore(name, version)

    def get(self, name: str) -> Optional[WorkflowDefinition]:
        """Return the active definition for a name, or None."""
        return self._ensure_context_manager().get(name)

    def get_info(self, name: str) -> Optional[WorkflowDefinition]:
        """Return the active definition for a name (capability-manager alias of get)."""
        return self._ensure_context_manager().get_info(name)

    def list(self) -> List[str]:
        """Return all registered workflow names, sorted."""
        return self._ensure_context_manager().list()

    def search(self, query: str) -> List[WorkflowDefinition]:
        """Return active workflows ranked by relevance to the query terms."""
        return self._ensure_context_manager().search(query)

    def get_instruction(self, allowlist=None) -> str:
        """Return the compact MetaAgent workflow roster, optionally allowlist-filtered."""
        return self._ensure_context_manager().get_instruction(allowlist=allowlist)

    async def function_callings(self, allowlist=None) -> List[Tuple[Dict[str, Any], Tuple[Any, ...]]]:
        """Return active workflows projected as native callable schemas."""
        return await self._ensure_context_manager().function_callings(allowlist=allowlist)

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Return the native callable schema for a workflow, or None if inactive/unknown."""
        return await self._ensure_context_manager().get_schema(name, action=action, format=format)

    def record_evaluation(self, evaluation: WorkflowEvaluation) -> WorkflowEvaluation:
        """Validate and persist one version-scoped evaluation record."""
        return self._ensure_context_manager().record_evaluation(evaluation)

    def evaluations(self, name: str) -> List[WorkflowEvaluation]:
        """Return evaluations recorded for the workflow's current version."""
        return self._ensure_context_manager().evaluations(name)

    def evaluation_summary(self, name: str) -> Dict[str, Any]:
        """Return the aggregate keep/optimize/rollback evaluation summary."""
        return self._ensure_context_manager().evaluation_summary(name)

    # Execution facade — WorkflowRuntime alone owns run state and checkpoints.
    async def run(self, name: str, *, input=None, ctx=None, depth=0, _budget=None) -> WorkflowRun:
        """Run a registered workflow to completion via the runtime and return its terminal run."""
        return await workflow_runtime.run(
            self._require(name), input=input, ctx=ctx, depth=depth, _budget=_budget,
        )

    def start(self, name: str, *, input=None, ctx=None, depth=0) -> str:
        """Start a registered workflow in the background and return its run id immediately."""
        return workflow_runtime.start(self._require(name), input=input, ctx=ctx, depth=depth)

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Return the in-memory run for an id, or None."""
        return workflow_runtime.get_run(run_id)

    def list_runs(self, workflow_name: Optional[str] = None) -> List[WorkflowRun]:
        """List retained runs (newest first), optionally filtered by workflow name."""
        return workflow_runtime.list_runs(workflow_name=workflow_name)

    def discard_run(self, run_id: str) -> bool:
        """Forget one terminal in-memory run (its on-disk checkpoint remains)."""
        return workflow_runtime.discard_run(run_id)

    def pause(self, run_id: str) -> bool:
        """Request a cooperative pause of a running workflow; returns True if accepted."""
        return workflow_runtime.pause(run_id)

    def continue_run(self, run_id: str) -> bool:
        """Resume an in-memory paused run without rebuilding completed work."""
        return workflow_runtime.continue_run(run_id)

    def cancel(self, run_id: str) -> bool:
        """Request cancellation of a run; returns True if the run was known."""
        return workflow_runtime.cancel(run_id)

    async def run_html(self, source: str, *, input=None, ctx=None) -> WorkflowRun:
        """Compile and run ephemeral Workflow HTML without registering it in the registry."""
        definition = workflow_compiler.compile(source).model_copy(update={"status": WorkflowStatus.EPHEMERAL})
        return await workflow_runtime.run(definition, input=input, ctx=ctx)

    async def resume(self, name: str, checkpoint: str, *, ctx=None, depth=0) -> WorkflowRun:
        """Resume a registered workflow from a checkpoint file via the runtime."""
        return await workflow_runtime.resume(self._require(name), checkpoint, ctx=ctx, depth=depth)

    def _require(self, name: str) -> WorkflowDefinition:
        """Return the active definition for a name, raising ValueError if unknown."""
        return self._ensure_context_manager().require(name)


# Backward-compatible class name; new code should prefer WorkflowManagerServer.
WorkflowManager = WorkflowManagerServer
workflow_manager = WorkflowManagerServer()

__all__ = ["WorkflowManager", "WorkflowManagerServer", "workflow_manager"]
