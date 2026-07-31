"""Custom deployer: the escape hatch — caller supplies image/build/start directly.

Use this for anything the built-in profiles don't cover (Go binary, Streamlit,
nginx config, a bespoke Dockerfile-style setup, …) without writing a new profile.
Everything is taken from ``request.overrides``; only ``start`` is required.
"""

from __future__ import annotations

from autogenesis.registry import DEPLOYER
from autogenesis.deploy.types import Deployer, DeploymentSpec, HealthCheck, DeployRequest


@DEPLOYER.register_module(name="custom", force=True)
class CustomDeployer(Deployer):
    name = "custom"
    description = "Fully caller-defined deployment (image/build/start via overrides)."
    default_image = "opensandbox/base:latest"
    default_port = 8000

    def make_spec(self, request: DeployRequest) -> DeploymentSpec:
        ov = dict(request.overrides or {})
        start = ov.get("start")
        if not start:
            raise ValueError(
                "custom runtime requires overrides.start (the server command, "
                "binding 0.0.0.0:<port>). Example overrides: "
                '{"image": "...", "build": ["..."], "start": "...", }'
            )
        port = request.port or ov.get("port") or self.default_port
        health = ov.get("health") or {"type": "http", "path": "/"}
        return DeploymentSpec(
            runtime=self.name,
            image=ov.get("image", self.default_image),
            workspace_root=ov.get("workspace_root", "/app"),
            build=list(ov.get("build", [])),
            start=start,
            port=port,
            health=HealthCheck(**health) if isinstance(health, dict) else health,
        )
