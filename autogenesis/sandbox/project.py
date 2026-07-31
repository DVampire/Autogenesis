"""Per-session filesystem sandbox and staged-extension promotion.

The agent never writes to the shared extension tree.  Each Project/Session owns
``<project_root>/extension`` as a writable staging tree; promotion is an
explicit, auditable copy into the shared extension root after validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from autogenesis.paths import P, path_manager
from autogenesis.utils import get_extension_root, get_package_root
from autogenesis.utils.path_utils import home_dir


_MODULES = ("tool", "agent", "prompt", "skill", "environment", "connector")
_DIRECTORY_MODULES = {"skill", "environment", "connector"}
_FILE_SUFFIX = {"tool": ".py", "agent": ".py", "prompt": ".html"}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_entry(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


@dataclass(frozen=True)
class ProjectSandbox:
    """Host-visible filesystem roots for one isolated Project/Session.

    ``workspace_root`` and ``extension_root`` are the only writable roots
    exposed to an agent.  The staged extension root is deliberately inside the
    project output tree, so users can inspect it locally before promotion.
    """

    project_root: Path
    workspace_root: Path
    log_root: Path
    extension_root: Path
    package_root: Path
    shared_extension_root: Path

    @classmethod
    def create(
        cls,
        project_root: str | Path,
        *,
        workspace_root: str | Path | None = None,
        package_root: str | Path | None = None,
        shared_extension_root: str | Path | None = None,
        materialize: bool = True,
    ) -> "ProjectSandbox":
        """Describe (and by default create) a session's sandbox roots.

        Pass ``materialize=False`` to only compute the paths.  A Gateway session is
        opened as soon as a client connects, but most never run anything; deferring
        creation until :meth:`materialize` (called when work actually starts) keeps
        empty session directories off disk.
        """
        project = Path(project_root).expanduser().resolve()
        workspace = Path(workspace_root).expanduser().resolve() if workspace_root else project / "workspace"
        log = project / "log"
        extension = project / "extension"
        if not _inside(workspace, project):
            raise ValueError("workspace_root must be located under project_root")
        if materialize:
            for root in (project, workspace, log, extension):
                root.mkdir(parents=True, exist_ok=True)
        return cls(
            project_root=project,
            workspace_root=workspace,
            log_root=log,
            extension_root=extension,
            package_root=Path(package_root or get_package_root()).expanduser().resolve(),
            shared_extension_root=Path(shared_extension_root or get_extension_root()).expanduser().resolve(),
        )

    def materialize(self) -> "ProjectSandbox":
        """Create this sandbox's roots on disk. Idempotent; safe to call repeatedly."""
        for root in (self.project_root, self.workspace_root, self.log_root, self.extension_root):
            root.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def manifest_path(self) -> Path:
        # Session audit state is user-level metadata, not project output. Pure path
        # computation — no directory is created here, so a session that never
        # promotes anything leaves no empty ``staging/`` tree behind (the dir is
        # created lazily by :meth:`_write_manifest`).
        project_key = hashlib.sha256(str(self.project_root).encode("utf-8")).hexdigest()[:16]
        return path_manager.get(P.STAGING, project_key=project_key) / "extension-staging.json"

    def describe(self) -> Dict[str, str]:
        """Return the host paths that map into a session sandbox."""
        return {
            "project_root": str(self.project_root),
            "workspace_root": str(self.workspace_root),
            "log_root": str(self.log_root),
            "extension_root": str(self.extension_root),
            "package_root": str(self.package_root),
            "shared_extension_root": str(self.shared_extension_root),
        }

    def mounts(self) -> List[Dict[str, str]]:
        """Expose only the session roots an agent is allowed to access."""
        return [
            {"source": str(self.workspace_root), "target": "/workspace", "mode": "rw"},
            {"source": str(self.extension_root), "target": "/extension", "mode": "rw"},
            {"source": str(self.package_root), "target": "/package", "mode": "ro"},
            {"source": str(self.shared_extension_root), "target": "/extension-base", "mode": "ro"},
        ]

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": 1, "promotions": []}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid staged-extension manifest: {exc}") from exc

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.manifest_path)

    def _entries(self) -> Iterable[tuple[str, Path]]:
        for module in _MODULES:
            module_root = self.extension_root / module
            if not module_root.is_dir():
                continue
            for entry in sorted(module_root.iterdir()):
                if entry.name.startswith("."):
                    continue
                if module in _DIRECTORY_MODULES:
                    if entry.is_dir():
                        yield module, entry
                elif entry.is_file() and entry.suffix == _FILE_SUFFIX[module]:
                    yield module, entry

    def staged_components(self) -> List[Dict[str, Any]]:
        """List files/directories eligible for promotion, without loading code."""
        components: List[Dict[str, Any]] = []
        for module, entry in self._entries():
            components.append({
                "module": module,
                "path": str(entry),
                "relative_path": str(entry.relative_to(self.extension_root)),
                "type": "directory" if entry.is_dir() else "file",
            })
        return components

    def validate(self, relative_paths: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Validate staged contents before a promotion without executing them."""
        components = self.staged_components()
        if relative_paths is not None:
            selected = {str(Path(path)) for path in relative_paths}
            components = [item for item in components if item["relative_path"] in selected]
            if len(components) != len(selected):
                raise ValueError("Requested staged extension component was not found")
        files = 0
        total_bytes = 0
        for component in components:
            entry = Path(component["path"])
            if entry.is_symlink() or not _inside(entry, self.extension_root):
                raise ValueError(f"Staged extension contains an unsafe component: {entry}")
            paths = [entry] if entry.is_file() else [path for path in entry.rglob("*") if path.is_file()]
            for path in paths:
                if path.is_symlink() or not _inside(path, self.extension_root):
                    raise ValueError(f"Staged extension contains an unsafe path: {path}")
                files += 1
                total_bytes += path.stat().st_size
                if path.suffix == ".py":
                    try:
                        compile(path.read_text(encoding="utf-8"), str(path), "exec")
                    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
                        raise ValueError(f"Python syntax check failed for {path}: {exc}") from exc
        return {"components": components, "file_count": files, "total_bytes": total_bytes}

    def promote(
        self,
        *,
        overwrite: bool = False,
        relative_paths: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Copy validated staged components into the shared extension tree.

        Existing targets are never overwritten unless requested.  When an overwrite
        is requested, the prior target is moved into a timestamped backup directory
        before the replacement is made.
        """
        report = self.validate(relative_paths)
        components = report["components"]
        if not components:
            return {**report, "promoted": [], "backup_root": None}

        self.shared_extension_root.mkdir(parents=True, exist_ok=True)
        promotion_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        backup_root = self.shared_extension_root / ".promotion-backups" / promotion_id
        promoted: List[Dict[str, str]] = []
        completed: List[tuple[Path, Optional[Path]]] = []
        try:
            for component in components:
                source = Path(component["path"])
                relative = Path(component["relative_path"])
                destination = self.shared_extension_root / relative
                if not _inside(destination, self.shared_extension_root):
                    raise ValueError(f"Promotion target escapes shared extension root: {destination}")
                backup: Optional[Path] = None
                if destination.exists():
                    if not overwrite:
                        raise FileExistsError(f"Refusing to overwrite shared extension component: {destination}")
                    backup = backup_root / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(backup))
                destination.parent.mkdir(parents=True, exist_ok=True)
                completed.append((destination, backup))
                if source.is_dir():
                    shutil.copytree(source, destination, symlinks=False)
                else:
                    shutil.copy2(source, destination)
                digest = _sha256(source) if source.is_file() else ""
                promoted.append({"module": component["module"], "source": str(source), "destination": str(destination), "sha256": digest})
        except Exception:
            for destination, backup in reversed(completed):
                if destination.exists() or destination.is_symlink():
                    _remove_entry(destination)
                if backup and backup.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup), str(destination))
            raise

        manifest = self._load_manifest()
        manifest.setdefault("promotions", []).append({
            "id": promotion_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "status": "copied",
            "overwrite": overwrite,
            "backup_root": str(backup_root) if backup_root.exists() else None,
            "components": promoted,
        })
        self._write_manifest(manifest)
        return {
            **report, "promotion_id": promotion_id, "promoted": promoted,
            "backup_root": str(backup_root) if backup_root.exists() else None,
        }

    def mark_promotion(self, report: Dict[str, Any], status: str) -> None:
        """Record the final registration outcome in the promotion audit log."""
        promotion_id = report.get("promotion_id")
        if not promotion_id:
            return
        manifest = self._load_manifest()
        for promotion in reversed(manifest.get("promotions", [])):
            if promotion.get("id") == promotion_id:
                promotion["status"] = status
                promotion["finished_at"] = datetime.now(timezone.utc).isoformat()
                self._write_manifest(manifest)
                return

    def rollback_promotion(self, report: Dict[str, Any]) -> None:
        """Restore filesystem state for a promotion whose registration failed."""
        backup_value = report.get("backup_root")
        backup_root = Path(backup_value).resolve() if backup_value else None
        for component in reversed(report.get("promoted", [])):
            destination = Path(component["destination"]).resolve()
            if not _inside(destination, self.shared_extension_root):
                raise ValueError(f"Rollback target escapes shared extension root: {destination}")
            _remove_entry(destination)
            if backup_root is not None:
                backup = backup_root / destination.relative_to(self.shared_extension_root)
                if backup.exists() or backup.is_symlink():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup), str(destination))
        self.mark_promotion(report, "rolled_back")


def staged_extension_root(ctx: Any) -> str:
    """Resolve the staged extension root from a session/agent context."""
    extra = getattr(ctx, "extra", {}) or {}
    return str(extra.get("extension_root") or get_extension_root())


def is_staged_extension_root(extension_root: str) -> bool:
    """Whether ``extension_root`` is a project staging tree, not the shared tree."""
    return bool(extension_root) and Path(extension_root).expanduser().resolve() != Path(get_extension_root()).resolve()


def validate_staged_extension(extension_root: str) -> Dict[str, Any]:
    """Validate a staged extension path supplied by a generation hook."""
    root = Path(extension_root).expanduser().resolve()
    sandbox = ProjectSandbox.create(root.parent)
    if sandbox.extension_root != root:
        raise ValueError(f"Invalid staged extension root: {extension_root}")
    return sandbox.validate()


def check_session_path(ctx: Any, path: str, *, write: bool) -> Optional[str]:
    """Return a denial reason when a session path escapes its sandbox roots.

    Contexts outside the Gateway do not carry ``project_root`` and retain legacy
    behavior.  Gateway sessions can read package/log/workspace/staging roots but
    may write only workspace and the staged extension tree.
    """
    extra = getattr(ctx, "extra", {}) or {}
    project_root = extra.get("project_root")
    if not project_root:
        return None
    candidate = Path(path).expanduser().resolve()
    writable = [Path(value).expanduser().resolve() for value in (extra.get("workspace_root"), extra.get("extension_root")) if value]
    readable = writable + [Path(value).expanduser().resolve() for value in (extra.get("package_root"), extra.get("log_root")) if value]
    allowed = writable if write else readable
    if any(_inside(candidate, root) for root in allowed):
        return None
    access = "write" if write else "read"
    roots = ", ".join(str(root) for root in allowed)
    return f"Sandbox denied {access} outside allowed roots: {path!r}. Allowed: {roots}"
