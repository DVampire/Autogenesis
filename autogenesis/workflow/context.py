"""Workflow registry context: discovery, contracts, prompt roster, and evidence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.utils import assemble_workspace_path
from autogenesis.version import version_manager
from autogenesis.capability import CapabilitySchema, SchemaSource

from .compiler import workflow_compiler
from .types import WorkflowDefinition, WorkflowEvaluation, WorkflowStatus


class WorkflowContextManager(BaseModel):
    """Own the non-execution lifecycle of registered HTML Workflows.

    This mirrors ToolContextManager and SkillContextManager: the context owns entity
    discovery, registry state, compact prompt context, native schemas, caches, and
    version-scoped evaluation evidence. WorkflowManagerServer remains a thin facade
    and delegates actual execution to WorkflowRuntime.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="Base directory for Workflow runtime context data")
    builtin_workflows_dir: str = Field(default=None, description="Directory containing built-in Workflow HTML")
    evaluation_path: str = Field(default=None, description="Persisted version-scoped evaluation evidence")

    def __init__(
        self,
        base_dir: Optional[str] = None,
        builtin_workflows_dir: Optional[str | Path] = None,
        evaluation_path: Optional[str | Path] = None,
        # Compatibility with the first Context implementation.
        builtin_dir: Optional[str | Path] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.base_dir = assemble_workspace_path(base_dir or os.path.join(config.log_root, "workflow"))
        selected_builtin_dir = builtin_workflows_dir or builtin_dir or (Path(__file__).parent / "default")
        self.builtin_workflows_dir = str(Path(selected_builtin_dir).resolve())
        self.evaluation_path = str(Path(evaluation_path or os.path.join(self.base_dir, "evaluations.json")))
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._workflow_history_versions: Dict[str, Dict[str, WorkflowDefinition]] = {}
        self._evaluations: Dict[str, List[WorkflowEvaluation]] = {}
        self._instruction_cache: Dict[Optional[Tuple[str, ...]], str] = {}
        logger.info(f"| 📁 Workflow context manager base directory: {self.base_dir}")

    async def initialize(self, workflow_names: Optional[List[str]] = None) -> None:
        """Load persisted evidence and discover built-in HTML definitions."""
        self._load_evaluations()
        builtin_dir = Path(self.builtin_workflows_dir)
        if not builtin_dir.exists():
            return
        selected = set(workflow_names) if workflow_names is not None else None
        for path in sorted(builtin_dir.glob("*.html")):
            if selected is None or path.stem in selected:
                definition = self.register(path, override=True)
                await version_manager.register_version("workflow", definition.name, definition.version)
        logger.info(f"| ✅ Workflows initialization completed — {len(self._definitions)} workflow(s) loaded")

    def register(
        self,
        workflow: WorkflowDefinition | str | Path,
        *,
        override: bool = False,
        status: Optional[str | WorkflowStatus] = None,
    ) -> WorkflowDefinition:
        """Compile and register one definition, invalidating derived context."""
        if isinstance(workflow, WorkflowDefinition):
            definition = workflow
        elif isinstance(workflow, Path) or (isinstance(workflow, str) and "<workflow" not in workflow):
            definition = workflow_compiler.compile_file(workflow)
        else:
            definition = workflow_compiler.compile(str(workflow))
        if status is not None:
            definition = definition.model_copy(update={"status": WorkflowStatus(status)})
        current = self._definitions.get(definition.name)
        if current is not None and not override:
            raise ValueError(f"Workflow {definition.name!r} is already registered")
        if (
            current is not None
            and current.version == definition.version
            and current.program_hash != definition.program_hash
        ):
            raise ValueError(
                f"Workflow {definition.name!r} changed executable content without a version increment"
            )
        self._definitions[definition.name] = definition
        self._workflow_history_versions.setdefault(definition.name, {})[definition.version] = definition
        self._invalidate_instruction()
        logger.info(f"| 📝 Registered Workflow '{definition.name}' v{definition.version}")
        return definition

    def unregister(self, name: str) -> bool:
        """Remove the active definition for a name and invalidate derived context.

        Returns:
            True if a definition was present and removed, False otherwise.
        """
        removed = self._definitions.pop(name, None) is not None
        if removed:
            self._invalidate_instruction()
            logger.info(f"| 🗑️ Unregistered Workflow '{name}'")
        return removed

    def restore(self, name: str, version: str) -> Optional[WorkflowDefinition]:
        """Restore an in-process historical definition and rebuild derived context."""
        definition = self._workflow_history_versions.get(name, {}).get(version)
        if definition is None:
            return None
        self._definitions[name] = definition.model_copy(deep=True)
        self._invalidate_instruction()
        logger.info(f"| 🔄 Restored Workflow '{name}' to v{version}")
        return self._definitions[name]

    def get(self, name: str) -> Optional[WorkflowDefinition]:
        """Return the active definition for a name, or None if not registered."""
        return self._definitions.get(name)

    def get_info(self, name: str) -> Optional[WorkflowDefinition]:
        """Alias of :meth:`get` matching the shared capability-manager interface."""
        return self.get(name)

    def list(self) -> List[str]:
        """Return the sorted names of all registered workflows."""
        return sorted(self._definitions)

    def search(self, query: str) -> List[WorkflowDefinition]:
        """Rank active workflows by how many query terms match their metadata.

        Args:
            query: Whitespace-separated search terms; empty query returns all active
                definitions.

        Returns:
            Active definitions whose name/description/applicability/tags match at least
            one term, ordered by descending match count.
        """
        terms = {term.lower() for term in query.split() if term}
        definitions = [
            self._definitions[name] for name in self.list()
            if self._definitions[name].status == WorkflowStatus.ACTIVE
        ]
        if not terms:
            return definitions

        def score(item: WorkflowDefinition) -> int:
            """Count how many query terms appear in the definition's searchable text."""
            haystack = " ".join([item.name, item.description, item.applicability, *item.tags]).lower()
            return sum(term in haystack for term in terms)

        return sorted((item for item in definitions if score(item)), key=score, reverse=True)

    def get_instruction(self, allowlist: Optional[List[str]] = None) -> str:
        """Render the compact MetaAgent roster; full HTML stays in inspect_workflow."""
        key = None if allowlist is None else tuple(allowlist)
        if key in self._instruction_cache:
            return self._instruction_cache[key]
        names = self.list() if allowlist is None else allowlist
        cards = []
        for name in names:
            item = self.get(name)
            if item is None or item.status != WorkflowStatus.ACTIVE:
                continue
            inputs = ", ".join(item.inputs) or "none"
            tags = ", ".join(item.tags) or "none"
            cards.append(
                f"- **{item.name}** (v{item.version}): {item.description or item.name}\n"
                f"  Inputs: {inputs}; Tags: {tags}"
            )
        text = "\n".join(cards)
        self._instruction_cache[key] = text
        return text

    async def function_callings(self, allowlist=None) -> List[Tuple[Dict[str, Any], Tuple[Any, ...]]]:
        """Project active registrations as native callable schemas."""
        if allowlist == []:
            return []
        names = allowlist if allowlist is not None else self.list()
        output = []
        for name in names:
            definition = self.get(name)
            if definition is None or definition.status != WorkflowStatus.ACTIVE:
                continue
            schema = await self.get_schema(name, format="json")
            if schema:
                output.append((schema, ("workflow", name)))
        return output

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Build the native callable schema (``workflow__<name>``) from input contracts.

        Assembles a JSON Schema object from the workflow's declared inputs, marking the
        result non-strict when any input fell back to a legacy inferred schema.

        Args:
            name: Registered workflow name.
            action: Unused; accepted for interface parity with other capability managers.
            format: Output format understood by :class:`CapabilitySchema` (``json`` or ``md``).

        Returns:
            The rendered schema, or None if the workflow is unknown or not active.
        """
        definition = self.get(name)
        if definition is None or definition.status != WorkflowStatus.ACTIVE:
            return None
        properties, required = {}, []
        for field, spec in definition.inputs.items():
            properties[field] = dict(spec.parameter_schema or {"type": spec.type})
            if spec.required:
                required.append(field)
        parameters: Dict[str, Any] = {
            "type": "object", "properties": properties, "additionalProperties": False,
        }
        if required:
            parameters["required"] = required
        source = (
            SchemaSource.LEGACY_FALLBACK
            if any(spec.schema_source == "legacy_fallback" for spec in definition.inputs.values())
            else SchemaSource.DECLARED
        )
        return CapabilitySchema(
            name=f"workflow__{name}", description=definition.description or name,
            parameters=parameters, strict=source != SchemaSource.LEGACY_FALLBACK, source=source,
        ).render(format)

    def record_evaluation(self, evaluation: WorkflowEvaluation) -> WorkflowEvaluation:
        """Validate and persist one version-scoped evaluation record.

        Successful evaluations must reference a real, terminal run whose identity and
        program hash match the registered contract; elapsed/token metrics are taken
        from that run rather than trusted from the caller. Static failure records need
        a ``case_id`` instead of a run. Duplicate run evidence is rejected.

        Args:
            evaluation: The evaluation to record; ``run_id``, metrics, and ``recorded_at``
                may be normalized before storage.

        Returns:
            The stored (possibly updated) evaluation record.

        Raises:
            ValueError: On version mismatch, missing/invalid run, non-terminal run,
                success/state disagreement, missing case_id, or duplicate evidence.
        """
        definition = self.require(evaluation.workflow_name)
        if evaluation.workflow_version != definition.version:
            raise ValueError("Evaluation version does not match the registered workflow")
        from .runtime import workflow_runtime

        run = workflow_runtime.get_run(evaluation.run_id) if evaluation.run_id else None
        if evaluation.run_id and run is None:
            raise ValueError("Evaluation run_id does not identify a retained Workflow run")
        if run is not None:
            if (run.workflow_name, run.workflow_version, run.program_hash) != (
                definition.name, definition.version, definition.program_hash,
            ):
                raise ValueError("Evaluation run does not match the registered Workflow contract")
            terminal = {"succeeded", "failed", "cancelled", "rejected"}
            if run.state.value not in terminal:
                raise ValueError("Evaluation run is not terminal")
            if evaluation.success != run.successful:
                raise ValueError("Evaluation success must match the recorded Workflow run")
            elapsed_ms = evaluation.elapsed_ms
            if run.started_at and run.finished_at:
                elapsed_ms = (
                    datetime.fromisoformat(run.finished_at) - datetime.fromisoformat(run.started_at)
                ).total_seconds() * 1000
            evaluation = evaluation.model_copy(update={
                "elapsed_ms": max(0.0, elapsed_ms),
                "token_cost": run.token_cost,
                "case_id": evaluation.case_id or evaluation.run_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            if evaluation.success:
                raise ValueError("A successful evaluation requires a real Workflow run_id")
            if not evaluation.case_id:
                raise ValueError("A static failure evaluation requires case_id")
            evaluation = evaluation.model_copy(update={
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })

        existing = self._evaluations.setdefault(definition.name, [])
        if evaluation.run_id and any(item.run_id == evaluation.run_id for item in existing):
            raise ValueError("This Workflow run has already been evaluated")
        existing.append(evaluation)
        self._save_evaluations()
        return evaluation

    def evaluations(self, name: str) -> List[WorkflowEvaluation]:
        """Return recorded evaluations for the workflow's currently registered version."""
        definition = self.get(name)
        if definition is None:
            return []
        return [
            item for item in self._evaluations.get(name, [])
            if item.workflow_version == definition.version
        ]

    def evaluation_summary(self, name: str) -> Dict[str, Any]:
        """Aggregate current-version evaluations into a keep/optimize/rollback signal.

        Returns:
            A dict with ``runs``, ``distinct_cases``, ``success_rate``, ``average_quality``,
            and a ``healthy`` flag (>=3 distinct cases, >=0.8 success, >=0.7 quality).
        """
        evaluations = self.evaluations(name)
        successes = [item for item in evaluations if item.success]
        distinct_cases = {item.case_id or item.run_id for item in evaluations if item.case_id or item.run_id}
        quality = sum(item.quality_score for item in evaluations) / len(evaluations) if evaluations else 0.0
        success_rate = len(successes) / len(evaluations) if evaluations else 0.0
        return {
            "healthy": len(distinct_cases) >= 3 and success_rate >= 0.8 and quality >= 0.7,
            "runs": len(evaluations),
            "distinct_cases": len(distinct_cases),
            "success_rate": success_rate,
            "average_quality": quality,
        }

    def require(self, name: str) -> WorkflowDefinition:
        """Return the active definition for a name, raising if it is not registered.

        Raises:
            ValueError: If no workflow is registered under the given name.
        """
        definition = self.get(name)
        if definition is None:
            raise ValueError(f"Unknown workflow: {name}")
        return definition

    def _invalidate_instruction(self) -> None:
        """Drop the cached prompt roster after any registry mutation."""
        self._instruction_cache.clear()

    def _load_evaluations(self) -> None:
        """Load persisted evaluation evidence, tolerating a missing or corrupt file."""
        path = Path(self.evaluation_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._evaluations = {
                name: [WorkflowEvaluation.model_validate(item) for item in items]
                for name, items in payload.items()
            }
        except Exception:
            # Corrupt optional evidence must not prevent the runtime from starting.
            self._evaluations = {}

    def _save_evaluations(self) -> None:
        """Atomically write all evaluation evidence to disk via a temp-file replace."""
        path = Path(self.evaluation_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: [item.model_dump() for item in items] for name, items in self._evaluations.items()}
        fd, temporary = tempfile.mkstemp(prefix=".evaluations-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def cleanup(self) -> None:
        """Release active registry state while retaining persisted evidence on disk."""
        self._definitions.clear()
        self._workflow_history_versions.clear()
        self._evaluations.clear()
        self._invalidate_instruction()
        logger.info("| 🧹 Workflow context manager cleaned up")


__all__ = ["WorkflowContextManager"]
