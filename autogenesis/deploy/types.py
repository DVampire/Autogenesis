"""Deployment subsystem base types.

A *deployment* runs one web service (static site / SPA / API / …) inside an
isolated sandbox container and binds it to a reachable URL. Like ``src/sandbox``
this is **infrastructure, not an evolvable LLM component**, so there is no
versioning/contract machinery here.

Two extension seams keep this open-ended (static site today, FastAPI/React/… and
later LLM inference tomorrow) without touching the manager:

* **Data-driven** — a :class:`DeploymentSpec` captures everything that varies by
  target (image, build steps, start command, port, health check, env, resources).
* **Code-driven** — a :class:`Deployer` *profile* knows how to turn a high-level
  :class:`DeployRequest` into a concrete :class:`DeploymentSpec` for one class of
  app. Profiles register with the ``DEPLOYER`` registry, so adding a new target
  type is "register a new Deployer", never "edit the manager".

The manager only ever executes a resolved spec (acquire → upload → build → start →
health-check → expose); it never knows React from FastAPI.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SiteStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"
    DETACHED = "detached"  # registry record survived but the sandbox handle is gone (e.g. after a process restart)


class HealthCheck(BaseModel):
    """How the manager decides a freshly-started service is *ready*."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="http", description="http | command | none")
    path: str = Field(default="/", description="HTTP path to probe when type=http.")
    command: Optional[str] = Field(
        default=None, description="Shell command (run in the container) that exits 0 when ready, for type=command."
    )
    timeout_s: int = Field(default=120, description="Max seconds to wait for readiness before declaring failure.")
    interval_s: float = Field(default=2.0, description="Seconds between probes.")


class ResourceSpec(BaseModel):
    """Requested container resources. ``gpu`` is a placeholder until the sandbox
    backend supports GPU passthrough (needed by the future ``llm`` profile)."""

    model_config = ConfigDict(extra="allow")

    cpu: Optional[float] = Field(default=None, description="CPU cores (best-effort; backend-dependent).")
    mem_mb: Optional[int] = Field(default=None, description="Memory in MB (best-effort; backend-dependent).")
    gpu: int = Field(default=0, description="GPU count — placeholder; opensandbox GPU support is TBD.")


class DeploymentSpec(BaseModel):
    """A fully-resolved, framework-agnostic recipe the manager executes.

    A :class:`Deployer` profile produces one of these from a :class:`DeployRequest`.
    """

    model_config = ConfigDict(extra="allow")

    runtime: str = Field(description="Profile that produced this spec (static/node/python/custom/…).")
    image: str = Field(description="Container image to run in.")
    workspace_root: str = Field(default="/app", description="Working directory inside the container (source is uploaded here).")
    build: List[str] = Field(
        default_factory=list, description="Shell commands run in workspace_root before start (fail-fast, in order)."
    )
    start: str = Field(
        description="Server start command. MUST bind 0.0.0.0:<port> (not 127.0.0.1) to be reachable via expose_port."
    )
    port: int = Field(description="The single primary port the service listens on; exposed as the site URL.")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables inside the container.")
    health: HealthCheck = Field(default_factory=HealthCheck)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    timeout_minutes: int = Field(default=120, description="Sandbox lifetime before opensandbox auto-kills it.")


class DeployRequest(BaseModel):
    """High-level deploy intent from the caller (the deploy_tool / an agent)."""

    model_config = ConfigDict(extra="allow")

    site_id: str = Field(description="Stable id for this site; also the sandbox reuse key.")
    runtime: str = Field(default="static", description="Deployer profile: static | node | python | custom | llm.")
    source_dir: Optional[str] = Field(default=None, description="Host directory uploaded into the container.")
    git_url: Optional[str] = Field(default=None, description="Git repo cloned inside the container (needs network).")
    port: Optional[int] = Field(default=None, description="Override the profile's default port.")
    env: Dict[str, str] = Field(default_factory=dict, description="Extra env vars merged into the spec.")
    overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Field-level overrides merged onto the resolved DeploymentSpec (image/build/start/health/workspace_root/…).",
    )


class SiteRecord(BaseModel):
    """Persisted record of one deployed site (the deployment registry entry)."""

    model_config = ConfigDict(extra="allow")

    site_id: str
    runtime: str
    status: SiteStatus = SiteStatus.PENDING
    url: Optional[str] = None
    port: Optional[int] = None
    image: Optional[str] = None
    backend: str = "opensandbox"  # which sandbox backend served it: opensandbox | host
    reuse_key: str = ""
    created_at: str = ""
    updated_at: str = ""
    error: Optional[str] = None
    log_path: str = Field(default="/tmp/deploy_site.log", description="In-container path of the server's stdout/stderr log.")
    request: Dict[str, Any] = Field(
        default_factory=dict, description="The original DeployRequest (dumped) so the site can be redeployed."
    )


class Deployer:
    """Base class for a runtime *profile*.

    A profile turns a :class:`DeployRequest` into a concrete :class:`DeploymentSpec`
    for one class of app. Subclass it, set ``name``/``default_image``/``default_port``,
    implement :meth:`make_spec`, and decorate with ``@DEPLOYER.register_module()``.
    Adding a new deployable target type is exactly this — no manager/tool changes.
    """

    name: str = "base"
    description: str = "Base deployer profile."
    default_image: str = "opensandbox/base:latest"
    default_port: int = 8000

    def make_spec(self, request: "DeployRequest") -> "DeploymentSpec":  # pragma: no cover - interface
        raise NotImplementedError
