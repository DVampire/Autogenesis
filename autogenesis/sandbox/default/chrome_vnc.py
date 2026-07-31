"""Headful Chrome + noVNC sandbox.

Behaves like :class:`PlaywrightSandbox` (drives Chrome over CDP), but runs the
browser HEADFUL on a virtual display with a VNC → websockify bridge, so the live
view can be watched over noVNC.  The image is built from ``docker/chrome-vnc/``
on first use (OpenSandbox runs over local Docker, so a locally-built tag works).

Exposes two proxied ports:
  9222  CDP  (inherited ``cdp_ws_url`` — Playwright connects here)
  6080  websockify (``vnc_ws_url`` — the frontend's noVNC client connects here)
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Optional

from autogenesis.logger import logger
from autogenesis.registry import SANDBOX
from autogenesis.sandbox.default.playwright import PlaywrightSandbox
from autogenesis.sandbox.types import SandboxConfig

# VNC/websockify ports are fixed inside the chrome-vnc container and mapped to
# ephemeral host ports by the opensandbox proxy — the browser sandbox's own
# concern, not a framework-global port.
NOVNC_PORT = 6080

_IMAGE = "autogenesis/chrome-vnc:latest"
# repo root: .../autogenesis/sandbox/default/chrome_vnc.py -> parents[3]
_DOCKERFILE_DIR = Path(__file__).resolve().parents[3] / "docker" / "chrome-vnc"


@SANDBOX.register_module(name="chrome-vnc", force=True)
class ChromeVncSandbox(PlaywrightSandbox):
    """Headful Chrome on a virtual display with a noVNC live view, reachable over CDP."""

    name: str = "chrome-vnc"
    description: str = "Headful Chrome with a noVNC live view, reachable over the DevTools protocol."
    default_image: str = _IMAGE
    # OpenSandbox launches the container with its OWN command: it ignores the
    # image's Dockerfile ENTRYPOINT and, when no entrypoint is passed, falls back
    # to a keep-alive `bootstrap.sh tail -f /dev/null`. So the VNC launcher must be
    # passed explicitly as the entrypoint — exactly like PlaywrightSandbox passes
    # ["/entrypoint"]. Leaving this None meant Xvfb/x11vnc/Chrome never started and
    # the CDP port (9222) was never opened.
    default_entrypoint = ["/usr/local/bin/entrypoint-vnc"]

    def __init__(self, config: Optional[SandboxConfig] = None, **kwargs: Any):
        super().__init__(config=config, **kwargs)

    async def start(self) -> None:
        await self._ensure_image()
        await super().start()

    async def _ensure_image(self) -> None:
        """Build the chrome-vnc image from docker/chrome-vnc/ if it isn't present."""
        image = self.config.image or self.default_image
        if image != _IMAGE or not shutil.which("docker"):
            return  # custom image, or no Docker to build with — leave it to the runtime
        if await self._docker(["image", "inspect", image], quiet=True) == 0:
            return  # already built
        if not (_DOCKERFILE_DIR / "Dockerfile").exists():
            logger.warning(f"| ⚠️ chrome-vnc: Dockerfile not found at {_DOCKERFILE_DIR}")
            return
        logger.info(f"| 🐳 Building {image} from {_DOCKERFILE_DIR} (first use; this can take a few minutes)…")
        code = await self._docker(["build", "-t", image, str(_DOCKERFILE_DIR)])
        if code != 0:
            logger.warning(f"| ⚠️ chrome-vnc: docker build failed (exit {code}); the sandbox may not start")

    @staticmethod
    async def _docker(args: list[str], *, quiet: bool = False) -> int:
        sink = asyncio.subprocess.DEVNULL if quiet else None
        proc = await asyncio.create_subprocess_exec("docker", *args, stdout=sink, stderr=sink)
        return await proc.wait()

    async def vnc_ws_url(self) -> str:
        """Return the websockify WebSocket URL the frontend's noVNC client connects to."""
        sb = self._require()
        endpoint = await sb.get_endpoint(NOVNC_PORT)
        host = getattr(endpoint, "endpoint", str(endpoint))  # e.g. 127.0.0.1:PORT/proxy/6080
        proxy_host = host.split("/proxy/")[0]
        self._register_host_port("novnc", proxy_host)
        return f"ws://{proxy_host}/proxy/{NOVNC_PORT}/websockify"
