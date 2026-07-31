"""Playwright/Chrome sandbox.

An OpenSandbox container running headless Chrome with the DevTools port exposed,
plus the proxy-rewrite needed to reach it over CDP. Used by the browser
environment and the artifact renderer to drive a page with Playwright
``connect_over_cdp``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from autogenesis.logger import logger
from autogenesis.registry import SANDBOX
from autogenesis.sandbox.default.base import OpenSandbox
from autogenesis.sandbox.types import SandboxConfig

# Fixed inside the browser container; the opensandbox proxy maps it to an
# ephemeral host port, so it is the browser sandbox's own concern, not a
# framework-global port.
CHROME_DEVTOOLS_PORT = 9222


@SANDBOX.register_module(name="playwright", force=True)
class PlaywrightSandbox(OpenSandbox):
    """OpenSandbox container running headless Chrome, reachable over CDP."""

    name: str = "playwright"
    description: str = "Sandboxed headless Chrome reachable over the DevTools protocol."
    default_image: str = "opensandbox/chrome:latest"
    default_entrypoint = ["/entrypoint"]

    def __init__(self, config: Optional[SandboxConfig] = None, **kwargs: Any):
        if config is None:
            config = SandboxConfig(**kwargs)
        if not config.timeout_minutes or config.timeout_minutes == 10:
            config.timeout_minutes = 30  # browser sessions are long-lived by default
        super().__init__(config)

    async def cdp_ws_url(self, *, attempts: int = 15, delay: float = 2.0) -> str:
        """Return a Playwright-connectable CDP WebSocket URL.

        Chrome reports a ws URL pointing at its container-internal port; we
        rewrite it to go through the opensandbox proxy endpoint.
        """
        sb = self._require()
        devtools = await sb.get_endpoint(CHROME_DEVTOOLS_PORT)
        host = getattr(devtools, "endpoint", str(devtools))  # e.g. 127.0.0.1:40697/proxy/9222
        proxy_base = f"http://{host}"
        proxy_host = host.split("/proxy/")[0]  # 127.0.0.1:40697

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{proxy_base}/json/version")
                    raw_ws = resp.json().get("webSocketDebuggerUrl", "")
                devtools_path = raw_ws.split(proxy_host, 1)[-1]  # /devtools/browser/<id>
                ws_url = f"ws://{proxy_host}/proxy/{CHROME_DEVTOOLS_PORT}{devtools_path}"
                logger.info(f"| 📦 CDP WebSocket URL: {ws_url}")
                self._register_host_port("cdp", proxy_host)
                return ws_url
            except Exception:
                if attempt == attempts - 1:
                    raise
                logger.info(f"| ⏳ Waiting for Chrome DevTools (attempt {attempt + 1}/{attempts})")
                await asyncio.sleep(delay)
        raise RuntimeError("Chrome DevTools did not become ready")

    def _register_host_port(self, purpose: str, proxy_host: str) -> None:
        """Register the host port this sandbox is reachable on into the port registry.

        The port itself is chosen by the opensandbox proxy (not by us); registering
        it keeps every port — including an environment's own — visible in one place.
        """
        try:
            port = int(str(proxy_host).rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            return
        from autogenesis.port import port_manager
        port_manager.register(f"{self.name}:{purpose}", port, type="env")
