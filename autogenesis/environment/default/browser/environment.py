"""Browser environment backed by Playwright."""

import base64
import io
import os
from typing import Any, Dict, List, Optional

from PIL import Image
from pydantic import ConfigDict, Field

from autogenesis.environment.default.browser.service import BrowserService
from autogenesis.environment.server import environment_manager
from autogenesis.environment.types import Environment, ScreenshotInfo, EnvironmentView
from autogenesis.logger import logger
from autogenesis.registry import ENVIRONMENT
from autogenesis.utils import ScreenshotService, assemble_workspace_path
from autogenesis.utils import encode_file_base64


def _b64_to_image(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))

@ENVIRONMENT.register_module(force=True)
class BrowserEnvironment(Environment):
    """Playwright-based browser environment."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="browser_environment")
    description: str = Field(default="Playwright browser environment for web automation")
    metadata: Dict[str, Any] = Field(default={"has_vision": True})
    enable_evolving: bool = Field(default=False)

    def __init__(
        self,
        base_dir: str = None,
        headless: bool = False,
        viewport: Optional[Dict[str, int]] = None,
        use_sandbox: bool = False,
        sandbox_domain: Optional[str] = None,   # None -> resolved via the port manager
        sandbox_api_key: Optional[str] = None,
        sandbox_image: str = "opensandbox/chrome:latest",
        sandbox_timeout_minutes: int = 30,
        use_som: bool = True,
        state_detail: str = "elements",
        max_state_elements: int = 0,  # 0 = no truncation (show all interactive elements)
        command_timeout: float = 30.0,
        vnc: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.base_dir = assemble_workspace_path(base_dir) if base_dir else assemble_workspace_path("browser")
        # A live noVNC view requires the browser to run headful in the chrome-vnc sandbox.
        self.vnc = vnc
        if vnc:
            headless = False
        self.headless = headless
        self.viewport = viewport or {"width": 1024, "height": 768}
        # State options: use_som draws numbered boxes on the state screenshot matching
        # the interactive-elements list; state_detail is "elements" (default) or "html".
        self.use_som = use_som
        self.state_detail = state_detail
        self.max_state_elements = max_state_elements
        self.command_timeout = command_timeout

        # Created lazily when a screenshot is actually saved — constructing the
        # environment (which happens at manager init, before any session is bound)
        # must not leave an empty directory behind.

        self._service = BrowserService(
            headless=headless,
            viewport=self.viewport,
            use_sandbox=use_sandbox,
            sandbox_domain=sandbox_domain,
            sandbox_api_key=sandbox_api_key,
            sandbox_image=sandbox_image,
            sandbox_timeout_minutes=sandbox_timeout_minutes,
            vnc=vnc,
        )
        # Per-session screenshot/step state, keyed by session_id (one browser tab
        # per session). Screenshots are stored under screenshots/<session_id>/.
        # step counts observation rounds; action_seq numbers actions within a round.
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._ss = ScreenshotService(base_dir=self.base_dir)

    # ------------------------------------------------------------------ lifecycle

    async def initialize(self) -> None:
        await self._service.start()
        logger.info(f"| 🌐 BrowserEnvironment ready at: {self.base_dir}")

    async def cleanup(self) -> None:
        await self._service.stop()
        self._sessions.clear()
        logger.info("| 🧹 BrowserEnvironment cleaned up")

    async def close_session(self, session_id: str) -> None:
        """Release a session's browser tab and per-session screenshot state."""
        self._sessions.pop(session_id or "default", None)
        await self._service.close_session(session_id or "default")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _session_id(ctx) -> str:
        return (getattr(ctx, "id", "") or "default") if ctx else "default"

    def _sess(self, ctx) -> tuple:
        """Return (session_id, per-session state record), creating it on first use."""
        sid = self._session_id(ctx)
        rec = self._sessions.get(sid)
        if rec is None:
            rec = {"step": 0, "action_seq": 0, "screenshot": None, "previous": None}
            self._sessions[sid] = rec
        return sid, rec

    def _make_screenshot_info(self, b64: str, path: str, description: str) -> ScreenshotInfo:
        return ScreenshotInfo(
            transformed=False,
            screenshot=b64,
            screenshot_path=path,
            screenshot_description=description,
            transform_info=None,
        )

    async def _save_annotated(self, img: Image.Image, suffix: str, sid: str, rec: Dict[str, Any]) -> str:
        rec["action_seq"] += 1
        filename = f"{sid}/step_{rec['step']:04d}_act{rec['action_seq']:02d}_{suffix}.png"
        path = await self._ss.store_screenshot(img, rec["step"], filename)
        return path

    def _wrap(self, result, extra_override: Dict = None) -> Dict[str, Any]:
        extra = result.extra.copy() if result.extra else {}
        if extra_override:
            extra.update(extra_override)
        return {"success": result.success, "message": result.message, "extra": extra}

    # ------------------------------------------------------------------ actions

    @environment_manager.action(name="click", description="Click at specified coordinates on the page")
    async def click(self, x: int, y: int, button: str = "left", ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            if rec["screenshot"]:
                img = _b64_to_image(rec["screenshot"].screenshot)
                img = await self._ss.draw_cursor(img, x, y)
                path = await self._save_annotated(img, "click", sid, rec)
                rec["previous"] = self._make_screenshot_info(
                    encode_file_base64(file_path=path), path, f"Action: Click at ({x}, {y}) with {button} button"
                )
            result = await self._service.click(x, y, button, session_id=sid)
            return self._wrap(result, {"x": x, "y": y, "button": button})
        except Exception as e:
            logger.error(f"| ❌ click failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="double_click", description="Double click at specified coordinates on the page")
    async def double_click(self, x: int, y: int, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            if rec["screenshot"]:
                img = _b64_to_image(rec["screenshot"].screenshot)
                img = await self._ss.draw_cursor(img, x, y)
                path = await self._save_annotated(img, "double_click", sid, rec)
                rec["previous"] = self._make_screenshot_info(
                    encode_file_base64(file_path=path), path, f"Action: Double-click at ({x}, {y})"
                )
            result = await self._service.double_click(x, y, session_id=sid)
            return self._wrap(result, {"x": x, "y": y})
        except Exception as e:
            logger.error(f"| ❌ double_click failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="scroll", description="Scroll at specified coordinates with given offsets")
    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            if rec["screenshot"]:
                img = _b64_to_image(rec["screenshot"].screenshot)
                img = await self._ss.draw_scroll(img, x, y, scroll_x, scroll_y)
                path = await self._save_annotated(img, "scroll", sid, rec)
                rec["previous"] = self._make_screenshot_info(
                    encode_file_base64(file_path=path), path,
                    f"Action: Scroll at ({x}, {y}) offset ({scroll_x}, {scroll_y})"
                )
            result = await self._service.scroll(x, y, scroll_x, scroll_y, session_id=sid)
            return self._wrap(result, {"x": x, "y": y, "scroll_x": scroll_x, "scroll_y": scroll_y})
        except Exception as e:
            logger.error(f"| ❌ scroll failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="type", description="Type text at the current cursor position")
    async def type_text(self, text: str, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, _ = self._sess(ctx)
            result = await self._service.type(text, session_id=sid)
            return self._wrap(result, {"text": text})
        except Exception as e:
            logger.error(f"| ❌ type failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="wait", description="Wait for specified milliseconds (default 1000)")
    async def wait(self, ms: int = 1000, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, _ = self._sess(ctx)
            result = await self._service.wait(ms, session_id=sid)
            return self._wrap(result, {"ms": ms})
        except Exception as e:
            logger.error(f"| ❌ wait failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="move", description="Move mouse to specified coordinates")
    async def move(self, x: int, y: int, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            if rec["screenshot"]:
                img = _b64_to_image(rec["screenshot"].screenshot)
                img = await self._ss.draw_cursor(img, x, y)
                path = await self._save_annotated(img, "move", sid, rec)
                rec["previous"] = self._make_screenshot_info(
                    encode_file_base64(file_path=path), path, f"Action: Move to ({x}, {y})"
                )
            result = await self._service.move(x, y, session_id=sid)
            return self._wrap(result, {"x": x, "y": y})
        except Exception as e:
            logger.error(f"| ❌ move failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="keypress", description="Press specified keys")
    async def keypress(self, keys: List[str], ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, _ = self._sess(ctx)
            result = await self._service.keypress(keys, session_id=sid)
            return self._wrap(result, {"keys": keys})
        except Exception as e:
            logger.error(f"| ❌ keypress failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(name="drag", description="Drag mouse along specified path")
    async def drag(self, path: List[List[int]], ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            if rec["screenshot"]:
                img = _b64_to_image(rec["screenshot"].screenshot)
                img = await self._ss.draw_path(img, path)
                save_path = await self._save_annotated(img, "drag", sid, rec)
                rec["previous"] = self._make_screenshot_info(
                    encode_file_base64(file_path=save_path), save_path,
                    f"Action: Drag along {len(path)} points"
                )
            result = await self._service.drag(path, session_id=sid)
            return self._wrap(result, {"path": path})
        except Exception as e:
            logger.error(f"| ❌ drag failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(
        name="goto",
        description="Navigate the browser to a URL. Accepts a full URL (https://...) or a bare domain. Use this to open a link found via the search action.",
    )
    async def goto(self, url: str, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, _ = self._sess(ctx)
            result = await self._service.goto(url, session_id=sid)
            return self._wrap(result, {"url": url})
        except Exception as e:
            logger.error(f"| ❌ goto failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(
        name="search",
        description=(
            "Search the web and get back a ranked list of results (title, URL, description) via the Firecrawl API. "
            "This runs server-side and is NOT blocked by local IP/CAPTCHA restrictions, so prefer it over navigating "
            "to a search engine. Use it to discover relevant pages, then open one with the `goto` action.\n"
            "Args: query (str), num_results (int, default 5)."
        ),
    )
    async def search(self, query: str, num_results: int = 5, **kwargs) -> Dict[str, Any]:
        try:
            result = await self._service.search(query, num_results=num_results)
            return self._wrap(result, {"query": query})
        except Exception as e:
            logger.error(f"| ❌ search failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    @environment_manager.action(
        name="command",
        description=(
            "Run a Playwright Python snippet with `page` (current Page) and `context` (BrowserContext) in scope. "
            "Use this as a fallback when coordinate-based actions fail (element not clickable, hidden, or moving), "
            "or to read structured data from the page. The code runs inside an async function: use `await` directly "
            "and `return` to send a value back. Timeout: 30s.\n"
            "Examples:\n"
            '- Click by text (auto-wait, auto-scroll, trusted event): await page.locator("text=Login").click()\n'
            '- Click by selector from the elements list: await page.locator("#submit").click()\n'
            '- Disambiguate multiple matches: await page.locator("button.submit").first.click()\n'
            '- Fill an input: await page.fill("input[name=\'q\']", "query")\n'
            '- Read data back: return await page.locator(".price").all_inner_texts()\n'
            '- Run JS in page: return await page.evaluate("document.title")\n'
            '- Wait for an element: await page.wait_for_selector("#result", timeout=5000)'
        ),
    )
    async def command(self, code: str, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, _ = self._sess(ctx)
            result = await self._service.command(code, timeout=self.command_timeout, session_id=sid)
            return self._wrap(result, {"code": code})
        except Exception as e:
            logger.error(f"| ❌ command failed: {e}")
            return {"success": False, "message": str(e), "extra": {"error": str(e)}}

    # ------------------------------------------------------------------ state

    def _render_elements_text(self, elements: List[Dict[str, Any]]) -> str:
        """Render the interactive-elements list as numbered lines for the LLM."""
        # max_state_elements <= 0 (or None) means show all elements, no truncation
        shown = elements[: self.max_state_elements] if self.max_state_elements else elements
        lines = []
        for el in shown:
            tag = f"<{el['tag']}" + (f" type={el['type']}" if el.get("type") else "") + ">"
            role = f" role={el['role']}" if el.get("role") else ""
            text = f' "{el["text"]}"' if el.get("text") else ""
            sel = f" selector={el['selector']}" if el.get("selector") else ""
            pos = f" center=({el['x']},{el['y']})"
            offscreen = ""
            if not el.get("in_viewport"):
                offscreen = " (below viewport, scroll down)" if el["top"] > 0 else " (above viewport, scroll up)"
            lines.append(f"[{el['index']}] {tag}{role}{text}{pos}{sel}{offscreen}")
        if len(elements) > len(shown):
            lines.append(f"... and {len(elements) - len(shown)} more elements not shown")
        return "\n".join(lines) if lines else "(no interactive elements detected)"

    async def live_view(self, ctx=None) -> Optional[EnvironmentView]:
        """Expose the headful browser's noVNC socket so the frontend can watch it live.

        Returns None unless running in VNC mode (headful in the chrome-vnc sandbox);
        the URL is the websockify endpoint the frontend's noVNC client connects to.
        """
        if not getattr(self, "vnc", False):
            return None
        url = await self._service.vnc_ws_url()
        if not url:
            return None
        return EnvironmentView(env_name=self.name, type="vnc", url=url, label="Browser (live)")

    async def get_state(self, ctx=None, **kwargs) -> Dict[str, Any]:
        try:
            sid, rec = self._sess(ctx)
            include_elements = self.state_detail in ("elements", "html")
            state_data = await self._service.get_state(
                include_elements=include_elements,
                include_html=self.state_detail == "html",
                session_id=sid,
            )

            elements = state_data.get("elements") or []
            scroll = state_data.get("scroll") or {}

            info_lines = [
                "<info>",
                f"Current URL: {state_data['url']}",
                f"Current Title: {state_data['title']}",
                f"Open Tabs: {state_data['tabs']}",
            ]
            if scroll:
                above = scroll.get("y", 0)
                below = max(0, scroll.get("page_height", 0) - scroll.get("viewport_height", 0) - above)
                info_lines.append(
                    f"Viewport: {scroll.get('viewport_width')}x{scroll.get('viewport_height')} | "
                    f"Scroll: {above}px above, {below}px below"
                    + (" (more content below)" if below > 0 else " (page bottom reached)")
                )
            info_lines.append(f"Focus: {state_data.get('focus', 'none')}")
            if state_data.get("iframes"):
                info_lines.append(
                    f"Iframes: {state_data['iframes']} present — elements inside iframes are NOT in the list; "
                    f"use `command` with page.frame_locator(...) to reach them"
                )
            info_lines.append("</info>")
            sections = ["\n".join(info_lines)]

            if include_elements:
                in_vp = sum(1 for el in elements if el.get("in_viewport"))
                sections.append(
                    f"<interactive_elements> ({len(elements)} total, {in_vp} in viewport"
                    + (", indices match the numbered boxes on the screenshot" if self.use_som else "")
                    + ")\n"
                    + self._render_elements_text(elements)
                    + "\n</interactive_elements>"
                )

            if self.state_detail == "html" and state_data.get("html"):
                sections.append(f"<page_html>\n{state_data['html']}\n</page_html>")

            state_text = "\n\n".join(sections)

            screenshots = []
            if state_data.get("screenshot"):
                step = rec["step"]
                img = _b64_to_image(state_data["screenshot"])
                # Keep the raw screenshot on disk for replay/debugging
                raw_path = await self._ss.store_screenshot(img, step, f"{sid}/step_{step:04d}_state_raw.png")
                description = "Browser state screenshot"
                if self.use_som and elements:
                    img = await self._ss.draw_som(img, elements)
                    description = "Browser state screenshot with numbered boxes matching the interactive elements list"
                path = await self._ss.store_screenshot(img, step, f"{sid}/step_{step:04d}_state.png")
                rec["screenshot"] = self._make_screenshot_info(
                    encode_file_base64(file_path=path), path, description
                )
                if not rec["previous"]:
                    rec["previous"] = rec["screenshot"]
                screenshots = [rec["previous"], rec["screenshot"]]

            # One observation round done — next round's actions number from act01
            rec["step"] += 1
            rec["action_seq"] = 0

            return {
                "state": state_text,
                "extra": {
                    "step_number": rec["step"],
                    "session_id": sid,
                    "headless": self.headless,
                    "viewport": self.viewport,
                    "base_dir": self.base_dir,
                    "screenshots": screenshots,
                    "url": state_data["url"],
                    "title": state_data["title"],
                    "tabs": state_data["tabs"],
                    "elements": elements,
                    "scroll": scroll,
                    "focus": state_data.get("focus", "none"),
                },
            }
        except Exception as e:
            logger.error(f"| ❌ get_state failed: {e}")
            return {"state": "Failed to get browser state", "extra": {"error": str(e)}}
