"""Canvas manager — session drafts, a JSON reuse library, and ephemeral runs.

The canvas stores everything as **JSON** and is isolated from the agent system's
``<workflow>`` HTML workflows (``extension/workflow/``). A canvas flow never
becomes an agent workflow and is never registered/callable by an agent.

- **Drafts** are session artifacts: JSON documents in a directory supplied by
  the caller (the Gateway passes ``<session project root>/canvas``).
- **Library** flows are the reuse store: ``export_to_library`` saves a flow as
  ``extension/canvas/<name>.json``; ``import_from_library`` loads it back as a
  fresh draft. The library surfaces as the ``canvas`` capability type (a
  human-facing library — not agent-callable).
- **Runs** compile in memory and start the shared workflow runtime as EPHEMERAL
  definitions; the canvas owns no executor and registers nothing.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from autogenesis.canvas.catalog import catalog
from autogenesis.canvas.compiler import canvas_compiler
from autogenesis.canvas.types import FlowGraph, NodeSpec, workflow_name_for
from autogenesis.logger import logger
from autogenesis.paths import P, path_manager
from autogenesis.utils import make_id

PUBLISHED_PREFIX = "wf:"


class CanvasManagerServer:
    """Stateless facade: draft directories are supplied per call by the Gateway."""

    async def initialize(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    async def catalog(self) -> List[NodeSpec]:
        return await catalog.build()

    async def mounts(self) -> Dict[str, Any]:
        """Global capability rosters the agent capability picker selects from."""
        return await catalog.build_mounts()

    # ------------------------------------------------------------------
    # Drafts (JSON under the session's output) + published extension flows
    # ------------------------------------------------------------------

    @staticmethod
    def _flow_path(flows_dir: Path, flow_id: str) -> Path:
        safe = "".join(char for char in flow_id if char.isalnum() or char in "-_")
        if not safe or safe != flow_id:
            raise ValueError(f"Invalid flow id: {flow_id!r}")
        return flows_dir / f"{safe}.json"

    def list_flows(self, flows_dir: Path) -> List[Dict[str, Any]]:
        """Summaries of this session's drafts. The reuse library is listed separately."""
        summaries: List[Dict[str, Any]] = []
        if flows_dir.is_dir():
            for path in sorted(flows_dir.glob("*.json")):
                try:
                    summaries.append(FlowGraph.model_validate_json(path.read_text(encoding="utf-8")).summary())
                except Exception as exc:  # noqa: BLE001 — one bad file must not hide the rest
                    logger.warning(f"| ⚠️ Canvas: unreadable flow file {path.name}: {exc}")
        summaries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return summaries

    def get_flow(self, flow_id: str, flows_dir: Path) -> FlowGraph:
        path = self._flow_path(flows_dir, flow_id)
        if not path.is_file():
            raise ValueError(f"Unknown flow: {flow_id}")
        return FlowGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def save_flow(self, graph: FlowGraph, flows_dir: Path) -> FlowGraph:
        """Persist a session draft. Drafts may be incomplete."""
        node_ids = {node.id for node in graph.nodes}
        if len(node_ids) != len(graph.nodes):
            raise ValueError("Duplicate node ids")
        for edge in graph.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"Edge {edge.id} references a missing node")
        now = datetime.now(timezone.utc).isoformat()
        if not graph.id:
            graph.id = f"flow-{make_id()}"
            graph.created_at = now
        graph.created_at = graph.created_at or now
        graph.updated_at = now
        flows_dir.mkdir(parents=True, exist_ok=True)
        path = self._flow_path(flows_dir, graph.id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(graph.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        return graph

    async def delete_flow(self, flow_id: str, flows_dir: Path) -> bool:
        path = self._flow_path(flows_dir, flow_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def flow_status(self, graph: FlowGraph) -> Dict[str, Any]:
        """Whether this flow is saved in the shared canvas reuse library (by name)."""
        name = workflow_name_for(graph)
        return {"name": name, "in_library": (self._library_dir() / f"{name}.json").is_file()}

    # ------------------------------------------------------------------
    # Canvas library — reusable flows saved as JSON under ``extension/canvas/``.
    # A human-facing reuse library, deliberately ISOLATED from the agent
    # system's workflows (which live as HTML DSL under ``extension/workflow/``).
    # Different storage format (JSON vs HTML) so the two never mix. The library
    # is not agent-callable: canvas flows are for people to compose and rerun.
    # ------------------------------------------------------------------

    @staticmethod
    def _library_dir() -> Path:
        from autogenesis.utils.path_utils import get_extension_root
        directory = Path(get_extension_root()) / "canvas"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def list_library(self) -> List[Dict[str, Any]]:
        """Summaries of every saved canvas library flow."""
        out: List[Dict[str, Any]] = []
        for path in sorted(self._library_dir().glob("*.json")):
            try:
                out.append(FlowGraph.model_validate_json(path.read_text(encoding="utf-8")).summary())
            except Exception as exc:  # noqa: BLE001 — one bad file must not hide the rest
                logger.warning(f"| ⚠️ Canvas library: unreadable {path.name}: {exc}")
        return out

    def list_library_names(self) -> List[str]:
        """Library flow names — the ``canvas`` capability type draws from this."""
        return [path.stem for path in sorted(self._library_dir().glob("*.json"))]

    def library_path(self, name: str) -> Path:
        return self._library_dir() / f"{name}.json"

    async def export_to_library(self, flow_id: str, flows_dir: Path) -> Dict[str, Any]:
        """Save a session draft into the shared canvas library (JSON) for reuse."""
        graph = self.get_flow(flow_id, flows_dir)
        name = workflow_name_for(graph)
        library_graph = graph.model_copy(deep=True)
        library_graph.id = ""  # a library copy is standalone, unbound from any session
        path = self.library_path(name)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(library_graph.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        logger.info(f"| 🎨 Canvas: exported '{name}' to the reuse library")
        return {"name": name, "artifact": str(path), "in_library": True}

    def import_from_library(self, name: str) -> FlowGraph:
        """Load a library flow as a fresh session draft (gets a new id on save)."""
        path = self.library_path(name)
        if not path.is_file():
            raise ValueError(f"Unknown canvas library flow: {name}")
        graph = FlowGraph.model_validate_json(path.read_text(encoding="utf-8"))
        graph.id = ""  # importing starts a new draft, never overwrites the library copy
        return graph

    async def delete_from_library(self, name: str) -> bool:
        path = self.library_path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    # ------------------------------------------------------------------
    # Default flows — example canvas flows shipped in ``canvas/default/``
    # (read-only templates). The picker offers them; selecting one loads it as
    # a fresh draft to run/edit. Managed here, never written to.
    # ------------------------------------------------------------------

    @staticmethod
    def _defaults_dir() -> Path:
        return Path(__file__).resolve().parent / "default"

    def list_defaults(self) -> List[Dict[str, Any]]:
        """Summaries of the shipped default flows (id = filename stem)."""
        out: List[Dict[str, Any]] = []
        directory = self._defaults_dir()
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    graph = FlowGraph.model_validate_json(path.read_text(encoding="utf-8"))
                    out.append({**graph.summary(), "id": path.stem})
                except Exception as exc:  # noqa: BLE001 — one bad file must not hide the rest
                    logger.warning(f"| ⚠️ Canvas defaults: unreadable {path.name}: {exc}")
        return out

    def list_default_names(self) -> List[str]:
        return [path.stem for path in sorted(self._defaults_dir().glob("*.json"))]

    def import_default(self, name: str) -> FlowGraph:
        """Load a default flow as a fresh draft (new id on save)."""
        path = self._defaults_dir() / f"{name}.json"
        if not path.is_file():
            raise ValueError(f"Unknown default flow: {name}")
        graph = FlowGraph.model_validate_json(path.read_text(encoding="utf-8"))
        graph.id = ""  # importing a template starts a new draft
        return graph

    # ------------------------------------------------------------------
    # Draft runs — ephemeral compile, straight into the workflow runtime
    # ------------------------------------------------------------------

    async def run_flow(self, graph: FlowGraph, input: Optional[Dict[str, Any]] = None, ctx: Any = None) -> str:
        from autogenesis.workflow.runtime import workflow_runtime
        from autogenesis.workflow.types import WorkflowStatus

        _, definition = canvas_compiler.compile(graph)
        definition = definition.model_copy(update={"status": WorkflowStatus.EPHEMERAL})
        return workflow_runtime.start(definition, input=input or {}, ctx=ctx)

    def run_status(self, run_id: str) -> Dict[str, Any]:
        """The full record of one run, live or finished.

        The runtime keeps runs in memory, so reopening a flow after a restart
        used to raise for every past run. The runtime also checkpoints each run
        to disk, which is the same record — so fall back to that file, and a
        history entry stays readable for as long as its checkpoint exists.
        """
        from autogenesis.workflow import workflow_manager

        run = workflow_manager.get_run(run_id)
        if run is not None:
            return run.model_dump(mode="json")
        checkpoint = path_manager.get(P.CHECKPOINTS) / f"{run_id}.json"
        if checkpoint.is_file():
            try:
                return json.loads(checkpoint.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 — a truncated checkpoint is not fatal
                logger.warning(f"| ⚠️ Canvas: unreadable checkpoint for run {run_id}: {exc}")
        raise ValueError(f"Unknown canvas run: {run_id}")

    # ------------------------------------------------------------------
    # Run history — one append-only index per flow, so reopening a flow can
    # show what it did last instead of an empty canvas.
    # ------------------------------------------------------------------

    @staticmethod
    def _runs_path(runs_dir: Path, flow_id: str) -> Path:
        safe = "".join(char for char in flow_id if char.isalnum() or char in "-_:")
        if not safe or safe != flow_id:
            raise ValueError(f"Invalid flow id: {flow_id!r}")
        return runs_dir / f"{safe}.jsonl"

    def record_run(self, flow_id: str, run_id: str, runs_dir: Path) -> None:
        """Note that ``flow_id`` produced ``run_id``. Appended when the run starts."""
        if not flow_id:
            return
        runs_dir.mkdir(parents=True, exist_ok=True)
        entry = {"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat()}
        with self._runs_path(runs_dir, flow_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list_runs(self, flow_id: str, runs_dir: Path, limit: int = 50) -> List[Dict[str, Any]]:
        """This flow's runs, newest first, each with its current state.

        The index holds only ids; the state is read back from the run itself, so
        a run that finished after the gateway restarted still reports correctly.
        """
        path = self._runs_path(runs_dir, flow_id)
        if not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:  # noqa: BLE001 — one bad line must not hide the rest
                continue
            try:
                record = self.run_status(entry["run_id"])
                entry.update({
                    "state": record.get("state"),
                    "started_at": record.get("started_at") or entry.get("started_at"),
                    "finished_at": record.get("finished_at"),
                    "error": record.get("error"),
                })
            except ValueError:
                entry["state"] = "unknown"  # checkpoint gone; the id is all we have
            out.append(entry)
            if len(out) >= limit:
                break
        return out

    def cancel_run(self, run_id: str) -> bool:
        from autogenesis.workflow import workflow_manager
        return workflow_manager.cancel(run_id)


# Global canvas manager instance
canvas_manager = CanvasManagerServer()

__all__ = ["CanvasManagerServer", "canvas_manager", "PUBLISHED_PREFIX"]
