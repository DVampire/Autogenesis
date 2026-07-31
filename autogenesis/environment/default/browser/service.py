"""Playwright-based browser service.

Supports two launch modes:
  - Local (default): launches a Chromium process via Playwright directly.
  - OpenSandbox: spins up an opensandbox/chrome container and connects via CDP.
"""

import asyncio
import base64
import textwrap
from datetime import timedelta
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from autogenesis.logger import logger
from autogenesis.environment.types import ActionResult


# Scans the page for visible interactive elements and collects scroll/focus info.
# Coordinates are CSS pixels relative to the viewport, matching page.mouse coordinates.
_OBSERVE_JS = """
() => {
  const SELECTOR = 'a, button, input, select, textarea, summary, ' +
    '[role=button], [role=link], [role=checkbox], [role=radio], [role=combobox], ' +
    '[role=menuitem], [role=tab], [role=option], [role=switch], [role=searchbox], ' +
    '[onclick], [contenteditable=true]';
  const vw = window.innerWidth, vh = window.innerHeight;
  const out = [];
  let idx = 1;
  for (const el of document.querySelectorAll(SELECTOR)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) === 0) continue;
    const text = (el.innerText || el.value || el.placeholder ||
      el.getAttribute('aria-label') || el.getAttribute('title') || '')
      .trim().replace(/\\s+/g, ' ').slice(0, 80);
    let selector = '';
    if (el.id) selector = '#' + CSS.escape(el.id);
    else if (el.getAttribute('name')) selector = el.tagName.toLowerCase() + '[name="' + el.getAttribute('name') + '"]';
    else if (el.getAttribute('aria-label')) selector = el.tagName.toLowerCase() + '[aria-label="' + el.getAttribute('aria-label') + '"]';
    out.push({
      index: idx++,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      role: el.getAttribute('role') || '',
      text: text,
      selector: selector,
      x: Math.round(r.left + r.width / 2),
      y: Math.round(r.top + r.height / 2),
      left: Math.round(r.left),
      top: Math.round(r.top),
      width: Math.round(r.width),
      height: Math.round(r.height),
      in_viewport: r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw,
    });
  }
  const ae = document.activeElement;
  return {
    elements: out,
    scroll: {
      x: Math.round(window.scrollX),
      y: Math.round(window.scrollY),
      page_width: Math.round(document.documentElement.scrollWidth),
      page_height: Math.round(document.documentElement.scrollHeight),
      viewport_width: vw,
      viewport_height: vh,
    },
    focus: ae && ae !== document.body
      ? ae.tagName.toLowerCase() + (ae.id ? '#' + ae.id : '') + (ae.getAttribute('name') ? '[name=' + ae.getAttribute('name') + ']' : '')
      : 'none',
    iframes: document.querySelectorAll('iframe').length,
  };
}
"""

# Returns page HTML with non-content nodes stripped (scripts, styles, svg, hidden elements).
_CLEAN_HTML_JS = """
() => {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('script, style, svg, noscript, link, meta, template').forEach(e => e.remove());
  return clone.outerHTML.replace(/\\n\\s*\\n/g, '\\n');
}
"""


class BrowserService:
    """Browser service backed directly by Playwright."""

    def __init__(
        self,
        headless: bool = True,
        viewport: Dict[str, int] = None,
        use_sandbox: bool = False,
        sandbox_domain: Optional[str] = None,   # None -> resolved via the port manager
        sandbox_api_key: Optional[str] = None,
        sandbox_image: str = "opensandbox/chrome:latest",
        sandbox_timeout_minutes: int = 30,
        vnc: bool = False,
    ):
        # VNC live view needs a headful browser in the chrome-vnc sandbox.
        self.vnc = vnc
        if vnc:
            use_sandbox = True
        self.headless = headless
        self.viewport = viewport or {"width": 1024, "height": 768}
        self.use_sandbox = use_sandbox
        self.sandbox_domain = sandbox_domain
        self.sandbox_api_key = sandbox_api_key
        self.sandbox_image = sandbox_image
        self.sandbox_timeout_minutes = sandbox_timeout_minutes
        self.sandbox_server_bin = "opensandbox-server"

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        # Per-session isolation: each session_id gets its own BrowserContext + Page
        # (independent cookies/storage) inside the one shared browser process.
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # Fallback context for CDP browsers that disallow new_context()
        self._base_context: Optional[BrowserContext] = None
        self._sandbox = None  # opensandbox Sandbox instance

    async def start(self):
        """Launch the browser. Pages are created lazily, one per session."""
        try:
            self._playwright = await async_playwright().start()

            if self.use_sandbox:
                await self._start_sandbox()
            else:
                await self._start_local()

            logger.info("| 🌐 BrowserService started")
        except Exception as e:
            logger.error(f"| ❌ Failed to start browser: {e}")
            # A failed start must not leak partial state: the acquired peer
            # container especially (an orphaned chrome sandbox breaks every
            # later boot), but also the Playwright driver process.
            await self._cleanup_failed_start()
            raise

    async def _cleanup_failed_start(self) -> None:
        async def _guard(label: str, coro, timeout: float = 20.0):
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except Exception as cleanup_error:  # noqa: BLE001 — best-effort teardown
                logger.warning(f"| ⚠️ Browser start-failure cleanup ({label}): {cleanup_error}")

        if self._browser:
            await _guard("browser.close", self._browser.close(), timeout=10.0)
        if self._sandbox:
            await _guard("sandbox.destroy", self._sandbox.destroy())
        if self._playwright:
            await _guard("playwright.stop", self._playwright.stop(), timeout=10.0)
        self._browser = None
        self._sandbox = None
        self._playwright = None
        self._base_context = None

    async def _start_local(self):
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._base_context = None  # create a fresh context per session
        logger.info("| 🖥️  Local Chromium launched")

    async def _start_sandbox(self):
        """Connect to a Chrome container via the sandbox subsystem.

        The PlaywrightSandbox (``autogenesis.sandbox``) owns the opensandbox-server
        daemon lifecycle, container creation, and the CDP proxy ws-url rewrite.
        """
        from autogenesis.sandbox import sandbox_manager

        # chrome-vnc runs headful Chrome + noVNC (for the live view); plain
        # playwright is headless. The chrome-vnc sandbox supplies its own image.
        sandbox_kind = "chrome-vnc" if self.vnc else "playwright"
        sandbox_image = None if self.vnc else self.sandbox_image
        self._sandbox = await sandbox_manager.acquire(
            sandbox_kind,
            image=sandbox_image,
            domain=self.sandbox_domain,
            api_key=self.sandbox_api_key,
            timeout_minutes=self.sandbox_timeout_minutes,
        )
        ws_url = await self._sandbox.cdp_ws_url()
        self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)
        contexts = self._browser.contexts
        # CDP-connected Chromium may not allow new_context(); keep the existing one as fallback
        self._base_context = contexts[0] if contexts else None

    async def vnc_ws_url(self) -> Optional[str]:
        """The websockify WS URL for the live view, or None when VNC isn't active."""
        sandbox = self._sandbox
        if not self.vnc or sandbox is None or not hasattr(sandbox, "vnc_ws_url"):
            return None
        try:
            return await sandbox.vnc_ws_url()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"| ⚠️ Could not resolve VNC url: {e}")
            return None

    async def stop(self):
        """Close all sessions and the browser.

        Each teardown step is time-boxed and isolated: a CDP close or a peer-container
        destroy that hangs (e.g. the chrome peer being torn down underneath the CDP
        connection) must not block the others — in particular the peer sandbox must
        always be destroyed so it can't leak, and the process can exit cleanly (which
        is what lets the launcher chown outputs back to the host user).
        """
        async def _guard(label: str, coro, timeout: float = 15.0):
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"| ⚠️ Browser teardown step timed out: {label}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"| ⚠️ Browser teardown step failed ({label}): {e}")

        for sid in list(self._sessions.keys()):
            await _guard(f"close_session {sid}", self.close_session(sid), timeout=5.0)
        if self._browser:
            await _guard("browser.close", self._browser.close(), timeout=10.0)
        if self._playwright:
            await _guard("playwright.stop", self._playwright.stop(), timeout=10.0)
        if self._sandbox:
            await _guard("sandbox.destroy", self._sandbox.destroy(), timeout=20.0)
        self._sessions.clear()
        self._base_context = None
        self._browser = None
        self._playwright = None
        self._sandbox = None
        logger.info("| 🛑 BrowserService stopped")

    # ------------------------------------------------------------------ session management

    async def _page_for(self, session_id: str = "default") -> Optional[Page]:
        """Return the Page for a session, lazily creating an isolated context+page."""
        if not self._browser:
            return None
        sess = self._sessions.get(session_id)
        if sess is None:
            owns_context = True
            try:
                context = await self._browser.new_context(viewport=self.viewport)
            except Exception:
                # Fall back to a shared base context (e.g. some CDP setups)
                context = self._base_context
                owns_context = False
                if context is None:
                    raise
            page = await context.new_page()
            try:
                await page.goto("about:blank")
            except Exception:
                pass
            sess = {"context": context, "page": page, "owns_context": owns_context}
            self._sessions[session_id] = sess
            logger.info(f"| 🪟 Browser session created: {session_id}")
        return sess["page"]

    async def close_session(self, session_id: str = "default") -> None:
        """Close a session's page and context (if we created it)."""
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return
        try:
            await sess["page"].close()
            if sess.get("owns_context") and sess.get("context"):
                await sess["context"].close()
            logger.info(f"| 🧹 Browser session closed: {session_id}")
        except Exception as e:
            logger.warning(f"| ⚠️ Error closing session {session_id}: {e}")

    # ------------------------------------------------------------------ helpers

    async def _screenshot_b64(self, page: Page) -> str:
        """Return a base64-encoded PNG screenshot of the given page."""
        data = await page.screenshot(type="png")
        return base64.b64encode(data).decode("utf-8")

    def _tabs(self, page: Page) -> List[str]:
        """Return URLs of all open pages in the page's context."""
        return [p.url for p in page.context.pages]

    def _unavailable(self, action: str) -> ActionResult:
        return ActionResult(
            success=False,
            message="Browser not available",
            extra={"error": "Browser not available", "action": action},
        )

    # ------------------------------------------------------------------ actions

    async def goto(self, url: str, wait_until: str = "domcontentloaded", session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("goto")
        try:
            if not url.startswith(("http://", "https://", "file://", "about:")):
                url = "https://" + url
            await page.goto(url, wait_until=wait_until, timeout=30000)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Navigated to {page.url}",
                extra={"screenshot": screenshot, "url": page.url},
            )
        except Exception as e:
            logger.error(f"| ❌ goto failed: {e}")
            return ActionResult(success=False, message=f"Failed to navigate to {url}: {e}", extra={"error": str(e)})

    async def search(self, query: str, num_results: int = 5) -> ActionResult:
        """Web search via Firecrawl (server-side crawl, bypasses local IP blocks).

        Returns title/url/description per result so the agent can pick a link and
        `goto` it. Does not touch the page — it's a pure API call.
        """
        from autogenesis.utils import hvac_client

        api_key = hvac_client.get("FIRECRAWL_API_KEY") or ""
        api_base = hvac_client.get("FIRECRAWL_API_BASE") or "https://api.firecrawl.dev/v2"
        if not api_key:
            return ActionResult(success=False, message="FIRECRAWL_API_KEY not set", extra={"error": "no_api_key"})
        if not query or not query.strip():
            return ActionResult(success=False, message="Search query cannot be empty", extra={"error": "empty_query"})

        import httpx
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"query": query.strip(), "limit": num_results}
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{api_base}/search", json=payload, headers=headers, timeout=httpx.Timeout(60.0))
                resp.raise_for_status()
                data = resp.json()

            raw = data.get("data", {})
            web = raw.get("web", []) if isinstance(raw, dict) else (raw or [])
            results = [
                {
                    "position": i + 1,
                    "title": it.get("title", "") or it.get("metadata", {}).get("title", ""),
                    "url": it.get("url", ""),
                    "description": it.get("description", "") or it.get("metadata", {}).get("description", ""),
                }
                for i, it in enumerate(web[:num_results])
            ]
            if not results:
                return ActionResult(success=True, message=f"No search results for: {query}", extra={"query": query, "results": []})

            lines = [f"[{r['position']}] {r['title']}\n    {r['url']}\n    {r['description']}" for r in results]
            return ActionResult(
                success=True,
                message=f"Search results for '{query}':\n" + "\n".join(lines),
                extra={"query": query, "results": results},
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"| ❌ search HTTP error: {e.response.status_code}")
            return ActionResult(success=False, message=f"Search failed: HTTP {e.response.status_code} — {e.response.text}", extra={"error": str(e)})
        except Exception as e:
            logger.error(f"| ❌ search failed: {e}")
            return ActionResult(success=False, message=f"Search failed: {e}", extra={"error": str(e)})

    async def click(self, x: int, y: int, button: str = "left", session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("click")
        try:
            await page.mouse.click(x, y, button=button)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Clicked at ({x}, {y}) with {button} button",
                extra={"screenshot": screenshot, "x": x, "y": y, "button": button},
            )
        except Exception as e:
            logger.error(f"| ❌ click failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def double_click(self, x: int, y: int, session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("double_click")
        try:
            await page.mouse.dblclick(x, y)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Double-clicked at ({x}, {y})",
                extra={"screenshot": screenshot, "x": x, "y": y},
            )
        except Exception as e:
            logger.error(f"| ❌ double_click failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int, session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("scroll")
        try:
            await page.mouse.move(x, y)
            await page.mouse.wheel(scroll_x, scroll_y)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Scrolled at ({x}, {y}) by ({scroll_x}, {scroll_y})",
                extra={"screenshot": screenshot, "x": x, "y": y, "scroll_x": scroll_x, "scroll_y": scroll_y},
            )
        except Exception as e:
            logger.error(f"| ❌ scroll failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def type(self, text: str, session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("type")
        try:
            await page.keyboard.type(text)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Typed: {text}",
                extra={"screenshot": screenshot, "text": text},
            )
        except Exception as e:
            logger.error(f"| ❌ type failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def wait(self, ms: int, session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("wait")
        try:
            await asyncio.sleep(ms / 1000.0)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Waited {ms}ms",
                extra={"screenshot": screenshot, "ms": ms},
            )
        except Exception as e:
            logger.error(f"| ❌ wait failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def move(self, x: int, y: int, session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("move")
        try:
            await page.mouse.move(x, y)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Moved to ({x}, {y})",
                extra={"screenshot": screenshot, "x": x, "y": y},
            )
        except Exception as e:
            logger.error(f"| ❌ move failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def keypress(self, keys: List[str], session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("keypress")
        try:
            combo = "+".join(keys)
            await page.keyboard.press(combo)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Pressed {keys}",
                extra={"screenshot": screenshot, "keys": keys},
            )
        except Exception as e:
            logger.error(f"| ❌ keypress failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def drag(self, path: List[List[int]], session_id: str = "default") -> ActionResult:
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("drag")
        try:
            if len(path) < 2:
                raise ValueError("Drag path must have at least 2 points")
            start = path[0]
            await page.mouse.move(start[0], start[1])
            await page.mouse.down()
            for point in path[1:]:
                await page.mouse.move(point[0], point[1])
            await page.mouse.up()
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Dragged along {len(path)} points",
                extra={"screenshot": screenshot, "path": path},
            )
        except Exception as e:
            logger.error(f"| ❌ drag failed: {e}")
            return ActionResult(success=False, message=str(e), extra={"error": str(e)})

    async def command(self, code: str, timeout: float = 30.0, session_id: str = "default") -> ActionResult:
        """Run a Playwright Python snippet with `page` and `context` in scope.

        The code is wrapped into an async function, so it may use `await`
        directly and `return` a value back to the caller.
        """
        page = await self._page_for(session_id)
        if not page:
            return self._unavailable("command")
        try:
            src = "async def __cmd__(page, context):\n" + textwrap.indent(code, "    ")
            ns: Dict[str, Any] = {}
            exec(src, ns)
            result = await asyncio.wait_for(ns["__cmd__"](page, page.context), timeout=timeout)
            result_repr = repr(result)
            screenshot = await self._screenshot_b64(page)
            return ActionResult(
                success=True,
                message=f"Command executed. Return value: {result_repr}",
                extra={"screenshot": screenshot, "result": result_repr},
            )
        except asyncio.TimeoutError:
            logger.error(f"| ❌ command timed out after {timeout}s")
            return ActionResult(
                success=False,
                message=f"Command timed out after {timeout}s. Locators auto-wait up to 30s by default; "
                        f"pass a shorter timeout in the code, e.g. page.locator(...).click(timeout=5000).",
                extra={"error": "timeout"},
            )
        except Exception as e:
            logger.error(f"| ❌ command failed: {e}")
            return ActionResult(success=False, message=f"Command failed: {e}", extra={"error": str(e)})

    async def observe(self, page: Page) -> Dict[str, Any]:
        """Scan the page for interactive elements, scroll position, and focus.

        Raises on page errors so get_state's retry loop can handle navigation races.
        """
        return await page.evaluate(_OBSERVE_JS)

    async def get_html(self, page: Page, max_chars: Optional[int] = None) -> str:
        """Return cleaned page HTML (scripts/styles/svg stripped).

        Full HTML by default; pass a positive max_chars to cap it.
        """
        try:
            html = await page.evaluate(_CLEAN_HTML_JS)
            if max_chars and len(html) > max_chars:
                html = html[:max_chars] + f"\n<!-- ... truncated, {len(html) - max_chars} more chars -->"
            return html
        except Exception as e:
            logger.error(f"| ❌ get_html failed: {e}")
            return ""

    async def get_state(self, include_elements: bool = True, include_html: bool = False, session_id: str = "default") -> Dict[str, Any]:
        """Return current page state for a session including a base64 screenshot."""
        empty = {"url": None, "title": None, "tabs": [], "screenshot": None,
                 "elements": [], "scroll": {}, "focus": "none", "iframes": 0, "html": ""}
        page = await self._page_for(session_id)
        if not page:
            return empty
        # Observing right after an action may race a navigation it triggered:
        # wait_for_load_state returns immediately on the old document, then
        # title/evaluate die with "Execution context was destroyed". Retry.
        last_error = None
        for attempt in range(3):
            try:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                url = page.url
                title = await page.title()
                tabs = self._tabs(page)
                screenshot = await self._screenshot_b64(page)
                state: Dict[str, Any] = {"url": url, "title": title, "tabs": tabs, "screenshot": screenshot,
                                         "elements": [], "scroll": {}, "focus": "none", "iframes": 0, "html": ""}
                if include_elements:
                    observed = await self.observe(page)
                    state.update({k: observed.get(k, state[k]) for k in ("elements", "scroll", "focus", "iframes")})
                if include_html:
                    state["html"] = await self.get_html(page)
                return state
            except Exception as e:
                last_error = e
                if "Execution context was destroyed" in str(e) or "navigat" in str(e).lower():
                    await asyncio.sleep(0.7)
                    continue
                break
        logger.error(f"| ❌ get_state failed: {last_error}")
        return empty
