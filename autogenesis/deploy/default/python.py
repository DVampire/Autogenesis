"""Python web-service deployer: FastAPI/Flask/ASGI apps served by uvicorn."""

from __future__ import annotations

from autogenesis.registry import DEPLOYER
from autogenesis.deploy.types import Deployer, DeploymentSpec, HealthCheck, DeployRequest


@DEPLOYER.register_module(name="python", force=True)
class PythonDeployer(Deployer):
    """Install requirements, then run an ASGI app with uvicorn bound to 0.0.0.0.

    Defaults to the ``app:app`` entrypoint (module ``app``, ASGI callable ``app``).
    For a different entrypoint (e.g. ``main:app``) or Flask/gunicorn, override
    ``start`` in the request, e.g. ``start='uvicorn main:app --host 0.0.0.0 --port 8000'``.
    """

    name = "python"
    description = "Deploy a Python web service (FastAPI/Flask/ASGI) via uvicorn."
    default_image = "python:3.11-slim"
    default_port = 8000

    def make_spec(self, request: DeployRequest) -> DeploymentSpec:
        port = request.port or self.default_port
        return DeploymentSpec(
            runtime=self.name,
            image=self.default_image,
            workspace_root="/app",
            build=[
                "if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi",
                "pip install --no-cache-dir 'uvicorn[standard]'",
            ],
            start=f"uvicorn app:app --host 0.0.0.0 --port {port}",
            port=port,
            # A connection that returns any HTTP status (even 404) means the server
            # is up; the manager's http probe treats "connection succeeded" as ready.
            health=HealthCheck(type="http", path="/", timeout_s=150),
        )
