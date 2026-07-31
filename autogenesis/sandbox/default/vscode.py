"""Full VS Code (openvscode-server) in a container, editing a session workspace.

One container per gateway session. The image is built from ``docker/vscode/`` on
first use, exactly like :class:`ChromeVncSandbox` builds ``docker/chrome-vnc/``
(OpenSandbox runs over local Docker, so a locally-built tag works).

Exposes one proxied port:
  3000  openvscode-server — HTTP *and* the workbench WebSocket, same port
        (``code_url`` — what the IDE manager hands the frontend to embed)
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Optional

from autogenesis.logger import logger
from autogenesis.registry import SANDBOX
from autogenesis.sandbox.default.base import OpenSandbox
from autogenesis.sandbox.types import SandboxConfig

# Fixed inside the container and mapped to an ephemeral host port by the
# opensandbox proxy — an IDE-local concern, not a framework-global port.
CODE_PORT = 3000

_IMAGE = "autogenesis/vscode:latest"
# repo root: .../autogenesis/sandbox/default/vscode.py -> parents[3]
_DOCKERFILE_DIR = Path(__file__).resolve().parents[3] / "docker" / "vscode"


@SANDBOX.register_module(name="vscode", force=True)
class VscodeSandbox(OpenSandbox):
    """openvscode-server serving one session workspace over HTTP."""

    name: str = "vscode"
    description: str = "Full VS Code (openvscode-server) editing the session workspace over HTTP."
    default_image: str = _IMAGE
    # OpenSandbox launches the container with its OWN command and ignores the
    # image's ENTRYPOINT, falling back to a keep-alive when none is passed — so
    # the launcher must be given explicitly or openvscode-server never starts
    # and port 3000 is never opened. Same reason chrome-vnc passes its own.
    default_entrypoint = ["/usr/local/bin/entrypoint-vscode"]

    def __init__(self, config: Optional[SandboxConfig] = None, **kwargs: Any):
        super().__init__(config=config, **kwargs)

    async def start(self) -> None:
        await self._ensure_image()
        await super().start()

    async def _ensure_image(self) -> None:
        """Build the vscode image from docker/vscode/ if it isn't present."""
        image = self.config.image or self.default_image
        if image != _IMAGE or not shutil.which("docker"):
            return  # custom image, or no Docker to build with — leave it to the runtime
        if await self._docker(["image", "inspect", image], quiet=True) == 0:
            return  # already built
        if not (_DOCKERFILE_DIR / "Dockerfile").exists():
            logger.warning(f"| ⚠️ vscode: Dockerfile not found at {_DOCKERFILE_DIR}")
            return
        logger.info(f"| 🐳 Building {image} from {_DOCKERFILE_DIR} (first use; this can take a few minutes)…")
        code = await self._docker(["build", "-t", image, str(_DOCKERFILE_DIR)])
        if code != 0:
            logger.warning(f"| ⚠️ vscode: docker build failed (exit {code}); the sandbox may not start")

    @staticmethod
    async def _docker(args: list[str], *, quiet: bool = False) -> int:
        sink = asyncio.subprocess.DEVNULL if quiet else None
        proc = await asyncio.create_subprocess_exec("docker", *args, stdout=sink, stderr=sink)
        return await proc.wait()

    async def port_url(self, port: int) -> str:
        """Base URL of the opensandbox proxy path for any port in this container.

        Shaped ``http://127.0.0.1:<ephemeral>/proxy/<port>``. The opensandbox
        proxy strips that prefix before forwarding, so the service inside always
        sees root-relative paths — which is what lets the frontend serve it at
        the root of a per-session host without the service knowing it is proxied.

        Generic on purpose: the IDE is only ever port 3000, but anything a user
        starts in the integrated terminal (a dev server, a preview, an OAuth
        callback listener) becomes reachable the same way, with no per-tool work.
        """
        sb = self._require()
        endpoint = await sb.get_endpoint(port)
        host = getattr(endpoint, "endpoint", str(endpoint))  # e.g. 127.0.0.1:PORT/proxy/3000
        proxy_host = host.split("/proxy/")[0]
        return f"http://{proxy_host}/proxy/{port}"

    async def code_url(self) -> str:
        """Base URL serving openvscode-server itself."""
        return await self.port_url(CODE_PORT)
