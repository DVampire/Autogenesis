"""ExtensionManager — loads hot-pluggable extensions from a flat `extension/` tree.

Framework code lives in `src/` (immutable). Evolved/generated components live outside
`src/`, under a flat working tree:

    extension/
    ├── manifest.json                 # active set: name -> active version + file
    ├── tool/<name>.py                # active source (normal, flat paths)
    ├── agent/<name>.py
    ├── prompt/<name>.html
    ├── skill/<name>/SKILL.md
    ├── environment/<name>/{environment.py + ENVIRONMENT.md}
    ├── connector/<name>/CONNECTOR.md
    ├── workflow/<name>.html
    └── .versions/<module>/<name>/<version>.<ext>   # archive: every version coexists

Authoring writes the flat active file; ExtensionManager archives each registered
version into `.versions/` so multiple versions of the same component coexist on disk,
and records the active version per component in `manifest.json`. Rollback copies an
archived version back over the active file and re-registers.

It is deliberately thin: loading is delegated to `dynamic_manager`, registration to
each `*_manager`, and per-component version numbering to `version_manager`.
"""

import os
import shutil
import tempfile
from inspect import isawaitable
from typing import Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from autogenesis.logger import logger
from autogenesis.utils import get_extension_root
from autogenesis.utils.file_utils import file_lock
from autogenesis.extension.types import Manifest, ManifestComponent

# Modules whose components are class-based (loaded via dynamic_manager).
_CLASS_MODULES = {"tool", "agent", "environment", "memory"}
# All modules the extension tree may carry.
_MODULES = ["tool", "agent", "prompt", "skill", "environment", "connector", "workflow", "memory"]
# Active-file extension per module ("" => the component is a directory).
_EXT = {"tool": ".py", "agent": ".py", "environment": "", "prompt": ".html", "skill": "", "connector": "", "workflow": ".html", "memory": ".py"}
# Directory-type modules: the active component is a directory holding a manifest file.
_DIR_MODULES = {"skill", "environment", "connector"}
_MANIFEST_FILE = {"skill": "SKILL.md", "environment": "ENVIRONMENT.md", "connector": "CONNECTOR.md"}
# For directory-type class modules, the Python class lives in this file inside the dir.
_CLASS_ENTRY = {"environment": "environment.py"}

_ARCHIVE = ".versions"

ExtensionChangeListener = Callable[[Dict[str, str]], Awaitable[None] | None]


class ExtensionManagerServer(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default="", description="Root directory of the extension tree")
    _change_listeners: set[ExtensionChangeListener] = PrivateAttr(default_factory=set)

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.base_dir = os.path.abspath(base_dir) if base_dir else get_extension_root()
        os.makedirs(self.base_dir, exist_ok=True)

    def set_base_dir(self, base_dir: str) -> None:
        """Select the configured project's durable extension directory."""
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def subscribe(self, listener: ExtensionChangeListener) -> None:
        """Receive hot-extension lifecycle changes after a component is live."""
        self._change_listeners.add(listener)

    def unsubscribe(self, listener: ExtensionChangeListener) -> None:
        self._change_listeners.discard(listener)

    async def _notify_change(
        self, action: str, module: str, name: str, *, version: Optional[str] = None
    ) -> None:
        change = {"action": action, "module": module, "name": name}
        if version:
            change["version"] = version
        for listener in tuple(self._change_listeners):
            try:
                result = listener(change)
                if isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"| ❌ ExtensionManager: change listener failed for {module}:{name}: {exc}",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def module_dir(self, module: str) -> str:
        return os.path.join(self.base_dir, module)

    def stage_path(self, module: str, filename: str) -> str:
        """Absolute path of the flat active file/dir a generator should write to."""
        mdir = self.module_dir(module)
        os.makedirs(mdir, exist_ok=True)
        return os.path.join(mdir, filename)

    def _archive_dir(self, module: str, name: str) -> str:
        return os.path.join(self.base_dir, _ARCHIVE, module, name)

    def _manifest_path(self) -> str:
        return os.path.join(self.base_dir, "manifest.json")

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------
    def read_manifest(self) -> Manifest:
        path = self._manifest_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return Manifest.model_validate_json(f.read())
        return Manifest()

    def _write_manifest(self, manifest: Manifest) -> None:
        """Durably replace the manifest; readers never observe partial JSON."""
        path = self._manifest_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(manifest.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def restore_manifest(self, manifest: Manifest) -> None:
        """Atomically restore and reload a previously captured active set."""
        async with file_lock(self._manifest_path()):
            self._write_manifest(manifest)
        await self.reload()

    # ------------------------------------------------------------------
    # Cold start
    # ------------------------------------------------------------------
    async def initialize(self) -> Manifest:
        """Load + register the active extension set.

        Prefers the manifest (loads each component at its recorded active version);
        falls back to scanning the flat module dirs on a fresh install. Call after the
        component managers have initialized their built-ins, so extensions layer on top.
        """
        manifest = self.read_manifest()
        if manifest.components:
            loaded: List[ManifestComponent] = []
            for comp in manifest.components:
                abspath = os.path.join(self.base_dir, comp.file)
                if not os.path.exists(abspath):
                    logger.warning(f"| ⚠️ ExtensionManager: active file missing for {comp.module}:{comp.name} ({abspath}); skipping.")
                    continue
                try:
                    await self._load_component(comp.module, abspath, comp.name, version=comp.version, config=None)
                    self._ensure_archived(comp.module, comp.name, abspath, comp.version)
                    loaded.append(comp)
                except Exception as e:
                    logger.error(f"| ❌ ExtensionManager: failed to load {comp.module}:{comp.name}: {e}")
            manifest.components = loaded
            self._write_manifest(manifest)
            logger.info(f"| ✅ ExtensionManager: loaded {len(loaded)} active extension components.")
            return manifest

        # Fresh install: scan flat dirs and register whatever is present.
        return await self._scan_and_load()

    async def _scan_and_load(self) -> Manifest:
        manifest = Manifest()
        for module in _MODULES:
            mdir = self.module_dir(module)
            if not os.path.isdir(mdir):
                continue
            ext = _EXT[module]
            for entry in sorted(os.listdir(mdir)):
                if entry.startswith(".") or entry == "__init__.py":
                    continue
                abspath = os.path.join(mdir, entry)
                if module in _DIR_MODULES:
                    if not (os.path.isdir(abspath) and os.path.exists(os.path.join(abspath, _MANIFEST_FILE[module]))):
                        continue
                elif not (entry.endswith(ext) and os.path.isfile(abspath)):
                    continue
                try:
                    name = await self._load_component(module, abspath, None, version=None, config=None)
                    comp = self._record(module, name, abspath, manifest)
                    self._ensure_archived(module, name, abspath, comp.version)
                except Exception as e:
                    logger.error(f"| ❌ ExtensionManager: failed to load {module}:{entry}: {e}")
        self._write_manifest(manifest)
        if manifest.components:
            logger.info(f"| ✅ ExtensionManager: discovered + loaded {len(manifest.components)} extension components.")
        else:
            logger.info("| 📦 ExtensionManager: no extension components found.")
        return manifest

    # ------------------------------------------------------------------
    # Authoring: hot-add / evolve a single component
    # ------------------------------------------------------------------
    async def add_component(self, module: str, abspath: str, config: Optional[dict] = None,
                            run_smoke: Optional[bool] = None) -> str:
        """Register an already-written flat active file, archive its version, update the manifest.

        Returns the registered component name. The version is assigned by the owning
        manager (via version_manager), so re-adding an existing component evolves it.

        ``run_smoke`` controls the replay gate for the newly registered component
        smoke run (see ``autogenesis/extension/smoke_gate.py``). On failure the component is
        rolled back to its previous version (or unloaded if brand-new) and
        ``EvolutionRejected`` is raised. Default (``None``) reads ``config.extension``
        ``smoke_gate`` and otherwise defaults on. Callers must explicitly pass
        ``run_smoke=False`` only for an already-validated administrative restore.
        """
        # add_component is the evolution-write entry point, so it enforces the
        # enable_evolving gate: overwriting an already-registered *frozen* entity is
        # refused here (rollback / reload / startup load do not pass this flag).
        name, version = await self._load_component(
            module, abspath, None, version=None, config=config, return_version=True, enforce_evolvable=True
        )
        # The manifest still holds the PREVIOUS active version here (it is rewritten
        # below), so this is the rollback target if the smoke gate fails
        # (None => brand-new component, which is unloaded instead of rolled back).
        _prev = self.read_manifest().find(module, name)
        prev_version = _prev.version if _prev else None
        # Serialize the manifest read-modify-write so parallel add_component calls
        # (e.g. concurrent component evolution) don't lose each other's updates.
        try:
            async with file_lock(self._manifest_path()):
                manifest = self.read_manifest()
                comp = self._record(module, name, abspath, manifest, version=version)
                # STRICT archive: guarantee a rollback target BEFORE committing the manifest.
                self._ensure_archived(module, name, abspath, comp.version)
                self._write_manifest(manifest)
        except Exception as e:
            # Transactional safety: we registered it live but cannot guarantee it is
            # recoverable (no archived version = nothing to roll back to). Unload the
            # half-committed component and fail, rather than leave an unrecoverable change live.
            logger.error(f"| ❌ ExtensionManager: add {module}:{name} not committed ({e}); unloading.")
            try:
                await self._unload_component(module, name)
            except Exception:
                pass
            raise
        logger.info(f"| ➕ ExtensionManager: added {module}:{name} v{comp.version}")

        if self._smoke_enabled(run_smoke):
            await self._smoke_gate_or_revert(module, name, prev_version)

        await self._notify_change(
            "registered" if prev_version is None else "evolved",
            module,
            name,
            version=comp.version,
        )
        return name

    def _smoke_enabled(self, run_smoke: Optional[bool]) -> bool:
        """Resolve the smoke gate; new/evolved code is verified by default."""
        if run_smoke is not None:
            return bool(run_smoke)
        try:
            from autogenesis.config import config
            ext_cfg = getattr(config, "extension", {}) or {}
            return bool(ext_cfg.get("smoke_gate", True)) if isinstance(ext_cfg, dict) else True
        except Exception:
            return True

    async def _smoke_gate_or_revert(self, module: str, name: str, prev_version: Optional[str]) -> None:
        """Run the replay smoke gate; on failure revert (rollback or unload) and raise."""
        from autogenesis.extension.smoke_gate import replay_smoke, EvolutionRejected

        report = await replay_smoke(module, name)
        if report.ok:
            return
        # Revert: roll back to the prior version, or unload a brand-new component.
        try:
            if prev_version is not None:
                await self.rollback(module, name, prev_version)
                logger.warning(f"| ⏪ ExtensionManager: {module}:{name} reverted to v{prev_version} (smoke gate).")
            else:
                await self.unload(module, name)
                logger.warning(f"| 🧹 ExtensionManager: {module}:{name} unloaded (smoke gate, no prior version).")
        except Exception as e:
            logger.error(f"| ❌ ExtensionManager: revert after failed smoke gate errored: {e}")
        raise EvolutionRejected(f"{module}:{name} rejected by replay smoke gate: {report.reason}")

    async def unload(self, module: str, name: str) -> bool:
        """Unregister an active component and drop it from the manifest (archive kept)."""
        ok = await self._unload_component(module, name)
        async with file_lock(self._manifest_path()):
            manifest = self.read_manifest()
            manifest.remove(module, name)
            self._write_manifest(manifest)
        if ok:
            await self._notify_change("unregistered", module, name)
        return ok

    async def deactivate_all(self) -> None:
        deactivated: List[ManifestComponent] = []
        async with file_lock(self._manifest_path()):
            manifest = self.read_manifest()
            for comp in list(manifest.components):
                if await self._unload_component(comp.module, comp.name):
                    deactivated.append(comp)
            self._write_manifest(Manifest())
        for comp in deactivated:
            await self._notify_change("unregistered", comp.module, comp.name)
        logger.info("| 🧹 ExtensionManager: deactivated all extensions.")

    async def reload(self) -> Manifest:
        """Re-load + re-register the active set (e.g. after editing flat files)."""
        manifest = self.read_manifest()
        for comp in manifest.components:
            abspath = os.path.join(self.base_dir, comp.file)
            if os.path.exists(abspath):
                try:
                    await self._load_component(comp.module, abspath, comp.name, version=comp.version, config=None)
                    await self._notify_change("reloaded", comp.module, comp.name, version=comp.version)
                except Exception as e:
                    logger.error(f"| ❌ ExtensionManager: reload failed for {comp.module}:{comp.name}: {e}")
        return manifest

    # ------------------------------------------------------------------
    # Versioning: list / read / diff / rollback
    # ------------------------------------------------------------------
    def read_component_version(self, module: str, name: str, version: str) -> Dict[str, str]:
        """Return the archived source of a version as ``{relative_path: text}``.

        Single-file modules (tool/agent/prompt) return one entry; directory modules
        (skill/environment/connector) return one entry per file in the archived dir.
        """
        ext = _EXT[module]
        path = os.path.join(self._archive_dir(module, name), f"{version}{ext}")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No archived {module}:{name} version '{version}' at {path}")
        out: Dict[str, str] = {}
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    rel = os.path.relpath(fp, path)
                    try:
                        out[rel] = open(fp, encoding="utf-8").read()
                    except Exception:
                        out[rel] = "<binary or unreadable>"
        else:
            # Single-file module: use a version-independent key (the component's canonical
            # filename) so the same logical file aligns across versions in a diff — the
            # archived filename is "<version><ext>", which would otherwise differ per version.
            key = f"{name}{ext}"
            try:
                out[key] = open(path, encoding="utf-8").read()
            except Exception:
                out[key] = "<binary or unreadable>"
        return out

    def diff_versions(self, module: str, name: str, version_a: str, version_b: Optional[str] = None) -> str:
        """Unified source diff between two archived versions.

        ``version_b`` defaults to the currently active version (from the manifest), so
        ``diff(module, name, old)`` shows what the live version changed relative to ``old``.
        """
        import difflib

        if version_b is None:
            comp = self.read_manifest().find(module, name)
            version_b = comp.version if comp else version_a
        a = self.read_component_version(module, name, version_a)
        b = self.read_component_version(module, name, version_b)
        chunks: List[str] = []
        for rel in sorted(set(a) | set(b)):
            if rel not in a:
                chunks.append(f"+++ added in {version_b}: {rel}")
                continue
            if rel not in b:
                chunks.append(f"--- removed in {version_b}: {rel}")
                continue
            d = list(difflib.unified_diff(
                a[rel].splitlines(keepends=True), b[rel].splitlines(keepends=True),
                fromfile=f"{version_a}/{rel}", tofile=f"{version_b}/{rel}",
            ))
            if d:
                chunks.append("".join(d))
        return "\n".join(chunks) if chunks else f"(no differences between v{version_a} and v{version_b})"

    def list_component_versions(self, module: str, name: str) -> List[str]:
        adir = self._archive_dir(module, name)
        if not os.path.isdir(adir):
            return []
        ext = _EXT[module]
        out = []
        for entry in os.listdir(adir):
            if module in _DIR_MODULES:
                if os.path.isdir(os.path.join(adir, entry)):
                    out.append(entry)
            elif entry.endswith(ext):
                out.append(entry[: -len(ext)] if ext else entry)
        return sorted(out)

    async def rollback(self, module: str, name: str, version: str, config: Optional[dict] = None) -> str:
        """Restore an archived version over the active file and re-register it."""
        ext = _EXT[module]
        archived = os.path.join(self._archive_dir(module, name), f"{version}{ext}")
        if not os.path.exists(archived):
            raise FileNotFoundError(f"No archived {module}:{name} version '{version}' at {archived}")

        # Determine the active flat destination (reuse the manifest's file if known).
        comp = self.read_manifest().find(module, name)
        if comp:
            dest = os.path.join(self.base_dir, comp.file)
        else:
            dest = os.path.join(self.module_dir(module), f"{name}{ext}")

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if module in _DIR_MODULES:
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(archived, dest)
        else:
            shutil.copyfile(archived, dest)

        loaded = await self._load_component(module, dest, name, version=version, config=config)
        async with file_lock(self._manifest_path()):
            manifest = self.read_manifest()
            self._record(module, loaded, dest, manifest, version=version)
            self._write_manifest(manifest)
        logger.info(f"| ⏪ ExtensionManager: rolled back {module}:{name} to v{version}")
        await self._notify_change("rolled_back", module, loaded, version=version)
        return loaded

    # ------------------------------------------------------------------
    # Internal: manifest record + archive
    # ------------------------------------------------------------------
    def _record(self, module: str, name: str, abspath: str, manifest: Manifest, version: Optional[str] = None) -> ManifestComponent:
        rel = os.path.relpath(abspath, self.base_dir)
        if version is None:
            existing = manifest.find(module, name)
            version = existing.version if existing else "1.0.0"
        comp = ManifestComponent(module=module, name=name, version=version, file=rel)
        manifest.upsert(comp)
        return comp

    def _ensure_archived(self, module: str, name: str, abspath: str, version: str) -> None:
        """Copy the active file into the version archive. STRICT: raises if the archive
        cannot be produced — a live version with no archived copy has no rollback target,
        so ``add_component`` treats an archiving failure as fatal rather than silent."""
        ext = _EXT[module]
        adir = self._archive_dir(module, name)
        os.makedirs(adir, exist_ok=True)
        dest = os.path.join(adir, f"{version}{ext}")
        if module in _DIR_MODULES:
            if os.path.abspath(abspath) != os.path.abspath(dest):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(abspath, dest)
        else:
            if os.path.abspath(abspath) != os.path.abspath(dest):
                shutil.copyfile(abspath, dest)
        if not os.path.exists(dest):
            raise RuntimeError(f"archiving {module}:{name} v{version} produced no file at {dest}")

    # ------------------------------------------------------------------
    # Per-module load / unload dispatch
    # ------------------------------------------------------------------
    async def _assert_evolvable(self, module: str, name: str) -> None:
        """Refuse to overwrite an already-registered *frozen* entity (enable_evolving=False).

        A brand-new entity (not yet registered) returns None → allowed. If the lookup
        itself ERRORS we **fail closed** (refuse the overwrite): we cannot confirm the
        target is not a frozen built-in, so blocking is the safe default — a genuine new
        component looks up cleanly as "not found" (None) and is unaffected.
        """
        try:
            current = await self._current_enable_evolving(module, name)
        except Exception as e:
            raise PermissionError(
                f"{module}:{name}: could not verify evolvability ({e}). Refusing the overwrite to "
                f"protect frozen built-ins (fail-closed). Retry once the registry is healthy."
            )
        if current is False:
            raise PermissionError(
                f"{module}:{name} is frozen (enable_evolving=False) and cannot be overwritten by "
                f"evolution. Set 'enable_evolving: true' on it first if you intend to evolve it."
            )

    async def _current_enable_evolving(self, module: str, name: str):
        """The currently-registered entity's enable_evolving flag, or None if not registered.

        Lookups return None cleanly for an unregistered name; any *exception* here is a real
        registry malfunction and is propagated so the caller can fail closed (see
        ``_assert_evolvable``) rather than silently allowing an overwrite.
        """
        if module == "tool":
            from autogenesis.tool.server import tool_manager
            inst = await tool_manager.get(name)
            return getattr(inst, "enable_evolving", None) if inst is not None else None
        if module == "agent":
            from autogenesis.agent.server import agent_manager
            info = await agent_manager.get_info(name)
            return getattr(info, "enable_evolving", None) if info is not None else None
        if module == "environment":
            from autogenesis.environment.server import environment_manager
            info = await environment_manager.get_info(name)
            return getattr(info, "enable_evolving", None) if info is not None else None
        if module == "skill":
            from autogenesis.skill.server import skill_manager
            info = await skill_manager.get_info(name)
            return getattr(info, "enable_evolving", None) if info is not None else None
        if module == "connector":
            from autogenesis.connector.server import connector_manager
            info = await connector_manager.get_info(name)
            return getattr(info, "enable_evolving", None) if info is not None else None
        if module == "workflow":
            from autogenesis.workflow import workflow_manager
            definition = workflow_manager.get(name)
            return getattr(definition, "enable_evolving", None) if definition is not None else None
        return None

    @staticmethod
    def _dir_component_name(abspath: str, md_name: str, default: str) -> str:
        """Read the `name:` from a dir component's SKILL.md/CONNECTOR.md frontmatter."""
        import re as _re
        import yaml as _yaml
        try:
            raw = open(os.path.join(abspath, md_name), encoding="utf-8").read()
            m = _re.match(r"^---\s*\n(.*?)\n---", raw, _re.DOTALL)
            fm = _yaml.safe_load(m.group(1)) if m else {}
            return (fm or {}).get("name") or default
        except Exception:
            return default

    async def _load_component(self, module: str, abspath: str, name_hint: Optional[str],
                              version: Optional[str], config: Optional[dict], return_version: bool = False,
                              enforce_evolvable: bool = False):
        if module in _CLASS_MODULES:
            return await self._load_class_component(module, abspath, version, config, return_version, enforce_evolvable)
        if module == "prompt":
            return await self._load_prompt(abspath, return_version)  # prompts carry no enable_evolving flag
        if module == "skill":
            return await self._load_skill(abspath, version, return_version, enforce_evolvable, config)
        if module == "connector":
            return await self._load_connector(abspath, version, return_version, enforce_evolvable, config)
        if module == "workflow":
            return await self._load_workflow(abspath, version, return_version, enforce_evolvable)
        raise ValueError(f"Unknown extension module: {module}")

    async def _load_class_component(self, module: str, abspath: str, version: Optional[str],
                                    config: Optional[dict], return_version: bool,
                                    enforce_evolvable: bool = False):
        from autogenesis.dynamic import dynamic_manager
        base_cls = self._base_class(module)
        # Directory-type class modules (environment) keep the class in a fixed entry
        # file inside the dir; single-file class modules (tool/agent) load the file itself.
        entry = _CLASS_ENTRY.get(module)
        if entry and os.path.isdir(abspath):
            class_file = os.path.join(abspath, entry)
            stem = os.path.basename(os.path.normpath(abspath))
        else:
            class_file = abspath
            stem = os.path.splitext(os.path.basename(abspath))[0]
        module_name = f"ext.{module}.{stem}"
        cls = dynamic_manager.load_class_from_path(
            class_file, base_class=base_cls, context=module, module_name=module_name
        )
        cls.__source_file__ = class_file
        with open(class_file, "r", encoding="utf-8") as f:
            code = f.read()

        if enforce_evolvable:
            fields = getattr(cls, "model_fields", {})
            intended = fields["name"].default if "name" in fields else getattr(cls, "name", stem)
            if isinstance(intended, str) and intended:
                await self._assert_evolvable(module, intended)

        if module == "tool":
            from autogenesis.tool.server import tool_manager
            cfg = await tool_manager.register(tool=cls, config=config or {}, code=code, override=True, version=version)
        elif module == "agent":
            from autogenesis.agent.server import agent_manager
            cfg = await agent_manager.register(agent_cls=cls, agent_config_dict=config, override=True, version=version)
        elif module == "environment":
            from autogenesis.environment.server import environment_manager
            cfg = await environment_manager.register(env_cls=cls, env_config_dict=config, override=True, version=version)
        elif module == "memory":
            from autogenesis.memory.server import memory_manager
            cfg = await memory_manager.register(cls, memory_config_dict=config, override=True, version=version)
        else:
            raise ValueError(f"Not a class-based module: {module}")
        name = getattr(cfg, "name", None) or getattr(cls, "__name__", "")
        return (name, getattr(cfg, "version", version or "1.0.0")) if return_version else name

    async def _load_prompt(self, abspath: str, return_version: bool):
        from autogenesis.prompt.server import prompt_manager
        from autogenesis.prompt.types import parse_prompt_file
        cfg = parse_prompt_file(abspath)
        if not cfg.name:
            stem = os.path.splitext(os.path.basename(abspath))[0]
            cfg = cfg.model_copy(update={"name": stem})
        registered = await prompt_manager.register(prompt=cfg.model_dump(), override=True)
        return (registered.name, getattr(registered, "version", "1.0.0")) if return_version else registered.name

    async def _load_skill(self, abspath: str, version: Optional[str], return_version: bool,
                          enforce_evolvable: bool = False, config: Optional[dict] = None):
        from autogenesis.skill.server import skill_manager
        if enforce_evolvable:
            await self._assert_evolvable("skill", self._dir_component_name(abspath, "SKILL.md", os.path.basename(abspath)))
        ev = (config or {}).get("enable_evolving")
        cfg = await skill_manager.register(skill_dir=abspath, override=True, version=version, enable_evolving=ev)
        name = getattr(cfg, "name", os.path.basename(abspath))
        return (name, getattr(cfg, "version", version or "1.0.0")) if return_version else name

    async def _load_connector(self, abspath: str, version: Optional[str], return_version: bool,
                              enforce_evolvable: bool = False, config: Optional[dict] = None):
        from autogenesis.connector.server import connector_manager
        if enforce_evolvable:
            await self._assert_evolvable("connector", self._dir_component_name(abspath, "CONNECTOR.md", os.path.basename(abspath)))
        ev = (config or {}).get("enable_evolving")
        cfg = await connector_manager.register(connector_dir=abspath, override=True, version=version, enable_evolving=ev)
        name = getattr(cfg, "name", os.path.basename(abspath))
        return (name, getattr(cfg, "version", version or "1.0.0")) if return_version else name

    async def _load_workflow(self, abspath: str, version: Optional[str], return_version: bool,
                             enforce_evolvable: bool = False):
        from autogenesis.version import version_manager
        from autogenesis.workflow import workflow_compiler, workflow_manager
        definition = workflow_compiler.compile_file(abspath)
        if enforce_evolvable:
            await self._assert_evolvable("workflow", definition.name)
        if version is None:
            current = await version_manager.get_current_version("workflow", definition.name)
            version = (
                await version_manager.generate_next_version("workflow", definition.name)
                if current else definition.version
            )
        definition = definition.model_copy(update={"version": version})
        workflow_manager.register(definition, override=True)
        await version_manager.register_version(
            "workflow", definition.name, definition.version,
            description=definition.description,
            metadata={"status": definition.status.value},
        )
        return (definition.name, definition.version) if return_version else definition.name

    async def _unload_component(self, module: str, name: str) -> bool:
        try:
            manager = self._manager(module)
            result = manager.unregister(name)
            ok = await result if isawaitable(result) else result
            logger.info(f"| 🧹 ExtensionManager: unregistered {module}:{name}")
            return bool(ok)
        except Exception as e:
            logger.warning(f"| ⚠️ ExtensionManager: failed to unregister {module}:{name}: {e}")
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _base_class(module: str):
        if module == "tool":
            from autogenesis.tool.types import Tool
            return Tool
        if module == "agent":
            from autogenesis.agent.types import Agent
            return Agent
        if module == "environment":
            from autogenesis.environment.types import Environment
            return Environment
        if module == "memory":
            from autogenesis.memory.types import Memory
            return Memory
        return None

    @staticmethod
    def _manager(module: str):
        if module == "tool":
            from autogenesis.tool.server import tool_manager
            return tool_manager
        if module == "agent":
            from autogenesis.agent.server import agent_manager
            return agent_manager
        if module == "prompt":
            from autogenesis.prompt.server import prompt_manager
            return prompt_manager
        if module == "skill":
            from autogenesis.skill.server import skill_manager
            return skill_manager
        if module == "environment":
            from autogenesis.environment.server import environment_manager
            return environment_manager
        if module == "connector":
            from autogenesis.connector.server import connector_manager
            return connector_manager
        if module == "workflow":
            from autogenesis.workflow import workflow_manager
            return workflow_manager
        if module == "memory":
            from autogenesis.memory.server import memory_manager
            return memory_manager
        raise ValueError(f"Unknown extension module: {module}")


# Global singleton
extension_manager = ExtensionManagerServer()
