"""Node/front-end deployer: build a JS app (React/Vue/Vite/CRA) and serve its output."""

from __future__ import annotations

from autogenesis.registry import DEPLOYER
from autogenesis.deploy.types import Deployer, DeploymentSpec, HealthCheck, DeployRequest


@DEPLOYER.register_module(name="node", force=True)
class NodeDeployer(Deployer):
    """Install deps, run the build, then serve the produced static bundle.

    The build output dir varies by tooling (Vite→``dist``, CRA→``build``,
    Next export→``out``), so the start command auto-detects it. For dev-server
    mode instead of a production build, override ``build``/``start`` in the request
    (e.g. ``start='npm run dev -- --host 0.0.0.0 --port 3000'``).
    """

    name = "node"
    description = "Build a JS/TS front-end (React/Vue/Vite/CRA) and serve the built bundle."
    default_image = "node:20-slim"
    default_port = 3000

    def make_spec(self, request: DeployRequest) -> DeploymentSpec:
        port = request.port or self.default_port
        # Detect the build output directory at start time, then serve it. `serve`
        # binds 0.0.0.0 by default. shlex-quoting in the manager keeps this safe.
        serve = (
            'DIR=dist; for d in dist build out public; do '
            'if [ -d "$d" ]; then DIR="$d"; break; fi; done; '
            f'npx --yes serve -s "$DIR" -l {port}'
        )
        return DeploymentSpec(
            runtime=self.name,
            image=self.default_image,
            workspace_root="/app",
            build=["npm ci || npm install", "npm run build"],
            start=serve,
            port=port,
            health=HealthCheck(type="http", path="/", timeout_s=180),
        )
