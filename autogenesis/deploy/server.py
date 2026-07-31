"""Deployment Manager Server.

``deployment_manager`` is the singleton entry point for the deployment subsystem.
It runs one web service per *site* inside an isolated OpenSandbox container and
binds it to a reachable URL, keeping a persisted registry of sites so they can be
listed / re-deployed / stopped.

Design (see ``autogenesis/deploy/types.py``): the manager is **framework-agnostic**. It
only knows the generic lifecycle —

    acquire sandbox → upload source → run build → start server (background)
    → expose_port → health-check → record in registry

The per-framework knowledge (image / build / start / health) lives in pluggable
:class:`~autogenesis.deploy.types.Deployer` profiles registered under ``DEPLOYER``. Adding
a new deployable target type is "register a new profile", never "edit this file".

Like ``sandbox_manager`` this carries no versioning machinery — a deployment is
infrastructure, not an evolvable component. Site handles live in-process (via
``sandbox_manager``); the JSON registry persists metadata so sites survive a
process restart as ``DETACHED`` records that ``redeploy`` can bring back.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict

from autogenesis.config import config
from autogenesis.paths import P, path_manager
from autogenesis.logger import logger
from autogenesis.registry import DEPLOYER
from autogenesis.sandbox import sandbox_manager
from autogenesis.deploy.types import (
    Deployer,
    DeploymentSpec,
    DeployRequest,
    HealthCheck,
    SiteRecord,
    SiteStatus,
)

# Directories skipped when uploading a host source tree into a container.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", ".cache", "dist", "build", ".DS_Store"}
_SANDBOX_KIND = "opensandbox"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeploymentManagerServer(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._sites: Dict[str, SiteRecord] = {}
        self._registry_path: Optional[str] = None
        self._initialized = False

    # --------------------------------------------------------------- lifecycle
    async def initialize(self, workspace_root: Optional[str] = None) -> None:
        """Load the persisted site registry and register built-in profiles. Idempotent."""
        if self._initialized:
            return
        import autogenesis.deploy.default  # noqa: F401  (registers built-in profiles with DEPLOYER)

        # Deployed sites are project-global and outlive any single session, so the
        # registry lives at ``output/.runtime/deploy`` (``P.DEPLOY``) rather
        # than a per-session log root — this keeps every session and every restart
        # looking at the same set of sites.
        from autogenesis.utils.path_utils import home_dir

        base = workspace_root or str(path_manager.get(P.DEPLOY, create=True))
        os.makedirs(base, exist_ok=True)
        self._registry_path = os.path.join(base, "sites.json")
        self._load()
        # After a restart the in-process sandbox handles are gone; re-probe each
        # recorded site so ones still serving are reattached as RUNNING and the
        # rest are marked DETACHED (redeployable).
        await self._reconcile_on_start()
        self._save()
        self._initialized = True
        logger.info(
            f"| 🚀 Deployment manager ready (profiles: {await self.list_profiles()}; "
            f"{len(self._sites)} site(s) in registry)"
        )

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    # --------------------------------------------------------------- discovery
    async def list_profiles(self) -> List[str]:
        import autogenesis.deploy.default  # noqa: F401
        return sorted(DEPLOYER.module_dict.keys())

    def _profile(self, runtime: str) -> Deployer:
        cls = DEPLOYER.get(runtime)
        if cls is None:
            raise ValueError(
                f"No deploy profile {runtime!r}. Available: {sorted(DEPLOYER.module_dict.keys())}"
            )
        return cls()

    # --------------------------------------------------------------- backend selection
    @staticmethod
    def _container_runtime_available() -> bool:
        """True if a Docker daemon (or remote host) is reachable — i.e. opensandbox can work."""
        if os.environ.get("DOCKER_HOST"):
            return True
        return os.path.exists("/var/run/docker.sock")

    def _backend_kind(self) -> str:
        """Pick the sandbox backend.

        ``DEPLOY_BACKEND`` env overrides: ``sandbox`` (opensandbox), ``host`` (local, no
        isolation), or ``auto`` (default): use opensandbox when a container runtime is
        available, else fall back to the host backend so deploys still work.
        """
        choice = (os.environ.get("DEPLOY_BACKEND") or "auto").lower().strip()
        if choice in ("host", "local"):
            return "host"
        if choice in ("sandbox", "opensandbox", "docker"):
            return "opensandbox"
        return "opensandbox" if self._container_runtime_available() else "host"

    def _host_site_dir(self, site_id: str) -> str:
        base = os.path.dirname(self._registry_path) if self._registry_path else os.path.join("workspace_root", "run", "deploy")
        return os.path.join(base, "sites", site_id, "app")

    @staticmethod
    def _reserve_host_port(site_id: str, preferred: int) -> int:
        """Register (and allocate) a host port for a host-backend site.

        Goes through the central ``port_manager`` so the binding lands in
        ``ports.json`` and is de-conflicted with everything else the framework
        binds.  Only host-backend sites need this — container backends have their
        own isolated port space.
        """
        from autogenesis.port import port_manager
        return port_manager.register(f"deploy:{site_id}", preferred=preferred, type="host")["port"]

    async def _reconcile_on_start(self) -> None:
        """Re-probe recorded sites at startup to recover ones still serving.

        A site's in-process sandbox handle does not survive a restart, but the
        service itself (a detached host process or a container) often does.  For
        each site that had a URL, probe it: reachable → RUNNING (reattached),
        otherwise DETACHED (its stored request can ``redeploy`` it).
        """
        for rec in self._sites.values():
            if rec.status in (SiteStatus.STOPPED, SiteStatus.FAILED):
                continue
            rec.status = SiteStatus.RUNNING if await self._url_reachable(rec.url) else SiteStatus.DETACHED

    @staticmethod
    async def _url_reachable(url: Optional[str]) -> bool:
        """True if ``url`` answers an HTTP request within a short timeout."""
        if not url:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                resp = await client.get(url)
            return resp.status_code < 500
        except Exception:
            return False

    # --------------------------------------------------------------- registry io
    def _load(self) -> None:
        if self._registry_path and os.path.exists(self._registry_path):
            try:
                with open(self._registry_path) as f:
                    raw = json.load(f)
                self._sites = {sid: SiteRecord(**rec) for sid, rec in raw.items()}
            except Exception as e:
                logger.warning(f"| ⚠️ Could not load deploy registry: {e}")
                self._sites = {}

    def _save(self) -> None:
        if not self._registry_path:
            return
        try:
            with open(self._registry_path, "w") as f:
                json.dump({sid: rec.model_dump() for sid, rec in self._sites.items()}, f, indent=2)
        except Exception as e:
            logger.warning(f"| ⚠️ Could not persist deploy registry: {e}")

    # --------------------------------------------------------------- spec resolution
    def _resolve_spec(self, request: DeployRequest) -> DeploymentSpec:
        """Profile → base spec, then overlay request.port / request.env / request.overrides."""
        spec = self._profile(request.runtime).make_spec(request)
        ov = dict(request.overrides or {})
        for field in ("image", "workspace_root", "build", "start", "timeout_minutes"):
            if field in ov and ov[field] is not None:
                setattr(spec, field, ov[field])
        if "health" in ov and ov["health"]:
            spec.health = HealthCheck(**ov["health"]) if isinstance(ov["health"], dict) else ov["health"]
        if request.port:
            spec.port = request.port
        if request.env:
            spec.env = {**spec.env, **request.env}
        return spec

    # --------------------------------------------------------------- deploy
    async def deploy(self, request: DeployRequest) -> SiteRecord:
        """Build and start a site in a fresh container, bind it to a URL, and record it."""
        await self._ensure_initialized()
        spec = self._resolve_spec(request)  # raises on bad profile / missing custom.start

        backend = self._backend_kind()
        # The host backend has no container filesystem, so run in a real host directory
        # and write the server log beside it (containers keep a per-container /tmp log).
        if backend == "host":
            spec.workspace_root = self._host_site_dir(request.site_id)
            log_path = os.path.join(os.path.dirname(spec.workspace_root), "server.log")
            # Host sites share the machine's ports: if the requested one is taken, move to
            # a free port and reflect it in the start command (literal port) and PORT env.
            free = self._reserve_host_port(request.site_id, spec.port)
            if free != spec.port:
                logger.info(f"| 🖥️  port {spec.port} busy → using free port {free} for '{request.site_id}'")
                spec.start = spec.start.replace(str(spec.port), str(free))
                spec.port = free
        else:
            log_path = "/tmp/deploy_site.log"

        # Expose the chosen port as $PORT so start commands using it (e.g. custom
        # `... --port $PORT`) resolve, regardless of backend.
        spec.env = {**spec.env, "PORT": str(spec.port)}

        rec = SiteRecord(
            site_id=request.site_id,
            runtime=spec.runtime,
            status=SiteStatus.BUILDING,
            port=spec.port,
            image=spec.image,
            backend=backend,
            reuse_key=request.site_id,
            created_at=self._sites.get(request.site_id, SiteRecord(site_id=request.site_id, runtime=spec.runtime)).created_at or _now(),
            updated_at=_now(),
            log_path=log_path,
            request=request.model_dump(),
        )
        self._sites[request.site_id] = rec
        self._save()

        try:
            if backend == "host":
                sandbox = await sandbox_manager.acquire(
                    "host", reuse_key=request.site_id, env=spec.env,
                    host_base=os.path.dirname(os.path.dirname(spec.workspace_root)),
                )
                logger.info(f"| 🖥️  '{request.site_id}': no container runtime → deploying on HOST (no isolation)")
            else:
                sandbox = await sandbox_manager.acquire(
                    _SANDBOX_KIND,
                    reuse_key=request.site_id,
                    image=spec.image,
                    env=spec.env,
                    timeout_minutes=spec.timeout_minutes,
                    network=True,
                )

            # --- upload source ---------------------------------------------------
            if request.git_url:
                res = await sandbox.run_command(f"git clone {shlex.quote(request.git_url)} {shlex.quote(spec.workspace_root)}")
                if not res.success:
                    raise RuntimeError(f"git clone failed: {res.as_message()}")
            else:
                await sandbox.run_command(f"mkdir -p {shlex.quote(spec.workspace_root)}")
                if request.source_dir:
                    await self._upload_dir(sandbox, request.source_dir, spec.workspace_root)

            # --- build (fail-fast) -----------------------------------------------
            for cmd in spec.build:
                res = await sandbox.run_command(cmd, workspace_root=spec.workspace_root, timeout=1800)
                if not res.success:
                    raise RuntimeError(f"build step failed ({cmd!r}): {res.as_message()}")

            # --- start server in the background ----------------------------------
            start_cmd = f"nohup sh -c {shlex.quote(spec.start)} > {shlex.quote(rec.log_path)} 2>&1 &"
            res = await sandbox.run_command(start_cmd, workspace_root=spec.workspace_root)
            if not res.success:
                raise RuntimeError(f"failed to launch start command: {res.as_message()}")

            # --- bind URL + wait until ready -------------------------------------
            url = await sandbox.expose_port(spec.port)
            ready = await self._health(sandbox, spec, url)
            if not ready:
                tail = await self._log_tail(sandbox, rec.log_path)
                raise RuntimeError(f"service did not become healthy within {spec.health.timeout_s}s. Log tail:\n{tail}")

            rec.url = url
            rec.status = SiteStatus.RUNNING
            rec.error = None
            rec.updated_at = _now()
            self._save()
            logger.info(f"| 🌐 Site '{request.site_id}' ({spec.runtime}) deployed at {url}")
            return rec
        except Exception as e:
            rec.status = SiteStatus.FAILED
            rec.error = str(e)
            rec.updated_at = _now()
            self._save()
            logger.error(f"| ❌ Deploy '{request.site_id}' failed: {e}")
            return rec

    async def _upload_dir(self, sandbox, source_dir: str, workspace_root: str) -> None:
        src_root = os.path.abspath(source_dir)
        if not os.path.isdir(src_root):
            raise RuntimeError(f"source_dir not found: {source_dir}")
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                host_path = os.path.join(root, fname)
                rel = os.path.relpath(host_path, src_root)
                dest = f"{workspace_root}/{rel}".replace(os.sep, "/")
                try:
                    with open(host_path, "rb") as fh:
                        await sandbox.write_file(dest, fh.read())
                except Exception as e:
                    logger.warning(f"| ⚠️ Skipped uploading {rel}: {e}")

    async def _health(self, sandbox, spec: DeploymentSpec, url: str) -> bool:
        """Poll readiness. http → GET the exposed URL from the host (image-agnostic);
        command → run a caller-supplied command in the container; none → ready at once."""
        hc = spec.health
        if hc.type == "none":
            return True
        # If the backend can tell us our launched server has died (e.g. failed to bind
        # its port), stop immediately — otherwise a stale/other server on the same port
        # could answer the probe and produce a false "healthy".
        alive_check = getattr(sandbox, "launched_alive", None)
        deadline = asyncio.get_event_loop().time() + hc.timeout_s
        probe_url = url.rstrip("/") + hc.path
        while asyncio.get_event_loop().time() < deadline:
            if alive_check is not None and not alive_check():
                logger.warning(f"| ⚠️ deploy: launched server process exited before becoming healthy")
                return False
            try:
                if hc.type == "command" and hc.command:
                    res = await sandbox.run_command(hc.command, workspace_root=spec.workspace_root, timeout=15)
                    if res.success:
                        return True
                else:  # http
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(probe_url)
                        if resp.status_code < 500:  # any response = the server is up
                            return True
            except Exception:
                pass
            await asyncio.sleep(hc.interval_s)
        return False

    async def _log_tail(self, sandbox, log_path: str, lines: int = 40) -> str:
        try:
            res = await sandbox.run_command(f"tail -n {lines} {shlex.quote(log_path)}")
            return res.as_message()
        except Exception:
            return "(no log available)"

    # --------------------------------------------------------------- queries / ops
    async def list_sites(self) -> List[SiteRecord]:
        await self._ensure_initialized()
        return list(self._sites.values())

    async def get_site(self, site_id: str) -> Optional[SiteRecord]:
        await self._ensure_initialized()
        return self._sites.get(site_id)

    async def stop_site(self, site_id: str) -> SiteRecord:
        await self._ensure_initialized()
        rec = self._sites.get(site_id)
        if rec is None:
            raise ValueError(f"No such site {site_id!r}")
        await sandbox_manager.release(rec.backend or _SANDBOX_KIND, reuse_key=site_id)
        rec.status = SiteStatus.STOPPED
        rec.url = None
        rec.updated_at = _now()
        self._save()
        logger.info(f"| 🛑 Site '{site_id}' stopped")
        return rec

    async def redeploy(self, site_id: str) -> SiteRecord:
        """Tear down and rebuild a site from its stored request (new URL likely)."""
        await self._ensure_initialized()
        rec = self._sites.get(site_id)
        if rec is None or not rec.request:
            raise ValueError(f"No redeployable request stored for site {site_id!r}")
        await sandbox_manager.release(rec.backend or _SANDBOX_KIND, reuse_key=site_id)
        return await self.deploy(DeployRequest(**rec.request))

    async def cleanup(self) -> None:
        """Stop all live sites (called on global teardown)."""
        for site_id, rec in list(self._sites.items()):
            try:
                await sandbox_manager.release(rec.backend or _SANDBOX_KIND, reuse_key=site_id)
            except Exception as e:
                logger.warning(f"| ⚠️ Error releasing site '{site_id}': {e}")


# Global deployment manager instance.
deployment_manager = DeploymentManagerServer()
