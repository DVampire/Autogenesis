"""Artifact renderer environment.

Renders self-contained HTML in an isolated headless Chrome and returns a
screenshot — the framework's local analogue of claude.ai Artifacts. Chrome runs
inside a sandbox (``autogenesis.sandbox`` PlaywrightSandbox) by default, so untrusted
generated markup never touches the host. A strict CSP meta tag is injected and
the HTML is loaded via Playwright ``set_content`` over CDP (no file serving
needed — works identically for local and sandboxed Chrome).

Pairs with the ``artifact_design_skill``: generate HTML → render here → look at
the screenshot → fix.
"""

import base64
import re
from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from autogenesis.environment.server import environment_manager
from autogenesis.environment.types import Environment
from autogenesis.logger import logger
from autogenesis.registry import ENVIRONMENT
from autogenesis.sandbox import sandbox_manager

_DEFAULT_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; "
    "img-src data: blob:; "
    "font-src data:; "
    "connect-src 'none'; "
    "frame-ancestors 'none'"
)

# crude detectors for resources a strict CSP would block
_EXTERNAL_PATTERNS = [
    (r"""<link[^>]+href=['"]https?://""", "external stylesheet/link"),
    (r"""<script[^>]+src=['"]https?://""", "external script"),
    (r"""<img[^>]+src=['"]https?://""", "remote image (use a data: URI)"),
    (r"""@import\s+(?:url\()?['"]?https?://""", "CSS @import of remote URL"),
    (r"""(?:fetch|XMLHttpRequest|WebSocket)\s*\(""", "network call (fetch/XHR/WebSocket)"),
    (r"""@font-face[^}]+url\(['"]?https?://""", "remote font (inline as data: URI)"),
]


@ENVIRONMENT.register_module(force=True)
class ArtifactRendererEnvironment(Environment):
    """Render self-contained HTML in a sandboxed headless Chrome → screenshot."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="artifact_renderer")
    description: str = Field(default="Render self-contained HTML in an isolated browser and screenshot it.")
    metadata: Dict[str, Any] = Field(default={"has_vision": True})
    enable_evolving: bool = Field(default=False)

    def __init__(
        self,
        use_sandbox: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        csp_policy: Optional[str] = None,
        max_html_size: int = 5_000_000,
        default_wait_ms: int = 800,
        sandbox_image: str = "opensandbox/chrome:latest",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.use_sandbox = use_sandbox
        self.viewport = viewport or {"width": 1024, "height": 768}
        self.csp_policy = csp_policy or _DEFAULT_CSP
        self.max_html_size = max_html_size
        self.default_wait_ms = default_wait_ms
        self.sandbox_image = sandbox_image

        self._playwright = None
        self._browser = None            # local-mode browser
        self._sessions: Dict[str, Any] = {}  # sid -> page

    # ------------------------------------------------------------ lifecycle
    async def initialize(self) -> None:
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        logger.info("| 🎨 ArtifactRendererEnvironment ready")

    async def cleanup(self) -> None:
        for page in list(self._sessions.values()):
            try:
                await page.close()
            except Exception:
                pass
        self._sessions.clear()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ------------------------------------------------------------ page acquisition
    async def _page_for(self, sid: str):
        if sid in self._sessions:
            return self._sessions[sid]

        if self.use_sandbox:
            sandbox = await sandbox_manager.acquire(
                "playwright", reuse_key=sid, image=self.sandbox_image
            )
            ws_url = await sandbox.cdp_ws_url()
            browser = await self._playwright.chromium.connect_over_cdp(ws_url)
            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context(viewport=self.viewport)
        else:
            if self._browser is None:
                self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context(viewport=self.viewport)

        page = await context.new_page()
        await page.set_viewport_size(self.viewport)
        self._sessions[sid] = page
        return page

    @staticmethod
    def _sid(ctx) -> str:
        return getattr(ctx, "id", None) or "default"

    # ------------------------------------------------------------ CSP helpers
    def _inject_csp(self, html: str) -> str:
        meta = f'<meta http-equiv="Content-Security-Policy" content="{self.csp_policy}">'
        if re.search(r"<head[^>]*>", html, re.IGNORECASE):
            return re.sub(r"(<head[^>]*>)", r"\1\n" + meta, html, count=1, flags=re.IGNORECASE)
        if re.search(r"<html[^>]*>", html, re.IGNORECASE):
            return re.sub(r"(<html[^>]*>)", r"\1<head>" + meta + "</head>", html, count=1, flags=re.IGNORECASE)
        return f"<head>{meta}</head>\n{html}"

    def _csp_violations(self, html: str):
        found = []
        for pat, label in _EXTERNAL_PATTERNS:
            if re.search(pat, html, re.IGNORECASE):
                found.append(label)
        return found

    # ------------------------------------------------------------ action
    @environment_manager.action(
        name="render_artifact",
        description="Render self-contained HTML in an isolated browser and return a screenshot. "
                    "Args: html (str), wait_ms (int, optional), validate_csp (bool, optional).",
    )
    async def render_artifact(
        self,
        html: str,
        wait_ms: Optional[int] = None,
        validate_csp: bool = True,
        ctx=None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not html or not html.strip():
            return {"success": False, "message": "empty html", "extra": {}}
        if len(html) > self.max_html_size:
            return {
                "success": False,
                "message": f"HTML exceeds max size ({len(html)} > {self.max_html_size})",
                "extra": {"error": "size_limit_exceeded"},
            }

        violations = self._csp_violations(html) if validate_csp else []
        render_html = self._inject_csp(html) if validate_csp else html
        wait = self.default_wait_ms if wait_ms is None else wait_ms

        try:
            sid = self._sid(ctx)
            page = await self._page_for(sid)
            await page.set_content(render_html, wait_until="networkidle")
            if wait:
                await page.wait_for_timeout(wait)
            png = await page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(png).decode("ascii")

            msg = "Rendered artifact."
            if violations:
                msg += " ⚠️ CSP-blocked resources detected (will not load): " + "; ".join(violations)
            return {
                "success": True,
                "message": msg,
                "extra": {
                    "screenshot": screenshot_b64,
                    "viewport": self.viewport,
                    "csp_validated": validate_csp,
                    "csp_violations": violations,
                },
            }
        except Exception as e:
            return {"success": False, "message": f"Render failed: {e}", "extra": {}}

    async def get_state(self, ctx=None, **kwargs) -> Dict[str, Any]:
        return {
            "state": "Artifact renderer ready.",
            "extra": {
                "use_sandbox": self.use_sandbox,
                "viewport": self.viewport,
                "csp_policy": self.csp_policy,
            },
        }
