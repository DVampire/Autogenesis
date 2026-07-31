"""Static-site deployer: serve a directory of pre-built files over HTTP."""

from __future__ import annotations

from autogenesis.registry import DEPLOYER
from autogenesis.deploy.types import Deployer, DeploymentSpec, HealthCheck, DeployRequest


@DEPLOYER.register_module(name="static", force=True)
class StaticDeployer(Deployer):
    """Serve static files (plain HTML/CSS/JS, or an already-built SPA) via
    Python's stdlib HTTP server. No build step."""

    name = "static"
    description = "Serve a directory of static files (HTML/CSS/JS or a pre-built SPA)."
    default_image = "python:3.11-slim"
    default_port = 8000

    def make_spec(self, request: DeployRequest) -> DeploymentSpec:
        port = request.port or self.default_port
        return DeploymentSpec(
            runtime=self.name,
            image=self.default_image,
            workspace_root="/app",
            build=[],
            start=f"python -m http.server {port} --bind 0.0.0.0",
            port=port,
            health=HealthCheck(type="http", path="/"),
        )
