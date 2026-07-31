"""Helpers for attaching every execution context to a project sandbox."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

import json
from datetime import datetime, timezone
from autogenesis.logger import logger
from autogenesis.paths import P, path_manager
from autogenesis.sandbox.project import ProjectSandbox
from autogenesis.config import config


#: Written into a session's project root once it exists, so the session can be
#: found again after a restart — and so a session started from a local config is
#: as visible to the browser as one the gateway created.
SESSION_MANIFEST = "session.json"


def write_session_manifest(
    sandbox: ProjectSandbox,
    *,
    session_id: str,
    owner: str = "local",
    name: str = "interactive",
    created_at: str | None = None,
    source_workspace: str | None = None,
) -> None:
    """Record a session's identity next to its files.

    Lives here rather than in the gateway so *whoever* creates a session writes
    the same manifest. When only the gateway did it, a locally-started run
    produced a directory the gateway could neither list nor restore — the same
    work, silently second-class depending on how it was launched.

    Deliberately small: identity and roots, no conversation history. The event
    log is a bounded in-memory ring, so a restored transcript would be a partial
    one pretending to be complete.
    """
    path = Path(sandbox.project_root) / SESSION_MANIFEST
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "session_id": session_id,
        "name": name,
        "owner": owner,
        "created_at": created_at or now,
        # Rewritten every time work happens, so the project list can lead with
        # what was touched last. ``created_at`` orders by birth, which puts a
        # project someone has been living in all week below one opened once and
        # abandoned.
        "updated_at": now,
        "source_workspace": source_workspace,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 — never fail a run over bookkeeping
        logger.warning(f"| ⚠️ Could not write session manifest for {session_id}: {exc}")


def ensure_session_sandbox(
    ctx: Any,
    project_root: str | Path | None = None,
    *,
    owner: str = "local",
    shared_extension_root: str | Path | None = None,
) -> ProjectSandbox | None:
    """Attach ``ctx`` to a deterministic per-session project if it has no roots.

    Gateway and CLI contexts already carry these roots.  This fallback brings the
    direct ``examples/run_*`` entry points under the same workspace boundary.

    With ``project_root`` omitted the session lands exactly where the gateway
    puts one — ``output/<owner>/sessions/<id>`` from the layout table — so a task
    started from a local config and the same task started from the browser use
    the same directory. Passing an explicit root stays available for tests and
    for callers that deliberately want their own tree.
    """
    extra = dict(getattr(ctx, "extra", {}) or {})
    if extra.get("project_root") and extra.get("workspace_root") and extra.get("extension_root"):
        return None

    session_id = str(getattr(ctx, "id", "") or "direct")
    root = (
        Path(project_root) / session_id if project_root is not None
        else path_manager.get(P.SESSION, owner=owner, session_id=session_id)
    )
    sandbox = ProjectSandbox.create(
        root,
        shared_extension_root=shared_extension_root,
    )
    write_session_manifest(
        sandbox,
        session_id=session_id,
        owner=owner,
        name=str(getattr(ctx, "name", "") or "interactive"),
    )
    ctx.extra = {**extra, **sandbox.describe()}
    return sandbox


def bind_session_roots(config: Any, sandbox: ProjectSandbox) -> None:
    """Move config-derived manager state from tag templates into one session."""
    old_workspace = Path(str(config.workspace_root)).resolve()
    old_log = Path(str(config.log_root)).resolve()

    def rebase(value: Any) -> None:
        if isinstance(value, dict):
            base_dir = value.get("base_dir")
            if isinstance(base_dir, str):
                candidate = Path(base_dir).expanduser().resolve()
                for source, target in ((old_workspace, sandbox.workspace_root), (old_log, sandbox.log_root)):
                    try:
                        value["base_dir"] = str(target / candidate.relative_to(source))
                        break
                    except ValueError:
                        continue
            for child in value.values():
                rebase(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                rebase(child)

    for value in config.values():
        rebase(value)
    log_name = Path(str(getattr(config, "log_path", "agent.log"))).name
    config.project_root = str(sandbox.project_root)
    config.workspace_root = str(sandbox.workspace_root)
    config.log_root = str(sandbox.log_root)
    config.log_path = str(sandbox.log_root / log_name)


def stage_input_files(ctx: Any, input: Dict[str, Any]) -> Dict[str, Any]:
    """Copy external task attachments into the session workspace before execution.

    Direct Python entry points commonly receive task documents from a checkout.  A
    sandboxed agent may not read those source paths, so their file inputs are copied
    into ``workspace/inputs`` and the agent receives only the staged paths.  Gateway
    uploads already live in the workspace and are left untouched.
    """
    prepared = dict(input)
    files = prepared.get("files")
    if not isinstance(files, list) or not config.workspace_root:
        return prepared

    workspace = Path(config.workspace_root).resolve()
    inputs_dir = workspace / "inputs"
    staged: list[str] = []
    for index, value in enumerate(files):
        source = Path(str(value)).expanduser().resolve()
        try:
            source.relative_to(workspace)
            staged.append(str(source))
            continue
        except ValueError:
            pass
        if not source.is_file():
            # Preserve a missing path so the receiving agent can report it normally.
            staged.append(str(source))
            continue
        inputs_dir.mkdir(parents=True, exist_ok=True)
        destination = inputs_dir / f"{index:03d}_{source.name}"
        shutil.copy2(source, destination)
        staged.append(str(destination))
    prepared["files"] = staged
    return prepared
