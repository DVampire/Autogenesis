"""Google Lens search — image + text search via browser-use BrowserSession."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.registry import TOOL
from autogenesis.tool.default.search.types import SearchItem
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType

CHROMIUM_PATH = "/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"


_DESCRIPTION = "Search Google Lens with an image file and an optional text query."

_INSTRUCTION = """
## Function
Search Google Lens with an image file and an optional text query.

## Guidance
- Returns the full result page as markdown content.

## Parameters
- query (str): Text query to combine with the image search.
- image (str): Path to the image file to search with.
- num_results (int, optional): Number of results to return (default: 10).
- filter_year (int, optional): Filter results by year (default: None).
- screenshot_dir (str, optional): Directory to save step screenshots into (default: None).

## Example
{"name": "google_lens_search_tool", "args": {"query": "identify this landmark", "image": "/path/to/photo.jpg"}}
"""


@TOOL.register_module(force=True)
class GoogleLensSearch(Tool):
    """Search using Google Lens with an image and optional text query.

    Uploads an image to Google Lens, optionally adds a text query,
    and returns the full result page as markdown.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "google_lens_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    chromium_path: str = Field(default=CHROMIUM_PATH, description="Path to Chromium binary")

    async def __call__(
        self,
        query: str,
        image: str,
        num_results: Optional[int] = 10,
        filter_year: Optional[int] = None,
        screenshot_dir: Optional[str] = None,
        **kwargs
    ) -> Response:
        """Execute a Google Lens search.

        Args:
            image: Path to the image file to search with.
            query: Optional text query to combine with the image search.
            screenshot_dir: Optional directory to save step screenshots into.
        """
        image_path = Path(image)
        if not image_path.exists():
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Image file not found: {image}",
            )

        try:
            md = await _run_lens_search(image_path, query, self.chromium_path, screenshot_dir)

            search_items: List[SearchItem] = [
                SearchItem(
                    title=f"Google Lens: {query}" if query else "Google Lens result",
                    url=f"https://lens.google.com",
                    description=query or "",
                    position=1,
                    source="google_lens",
                    content=md,
                )
            ]

            results_json = json.dumps(
                [
                    {
                        "title": item.title,
                        "url": item.url,
                        "description": item.description or "",
                        "position": item.position,
                        "content": item.content or "",
                    }
                    for item in search_items
                ],
                ensure_ascii=False,
                indent=4,
            )

            message = f"Google Lens search results for query: {query}\n\n{results_json}"

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                data={
                    "image": str(image_path),
                    "query": query,
                    "num_results": 1,
                    "search_items": search_items,
                    "engine": "google_lens",
                },
            )
        except Exception as e:
            logger.error(f"| GoogleLensSearch error: {e}")
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Google Lens search failed: {str(e)}",
            )


async def _save_screenshot(page, screenshot_dir: Optional[Path], name: str):
    """Save a debug screenshot of the page as ``<name>.png``, if enabled.

    No-op when `screenshot_dir` is None; otherwise creates the directory and
    decodes the browser's base64 screenshot to disk. Used to trace the Lens flow.
    """
    if screenshot_dir is None:
        return
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    b64 = await page.screenshot()
    (screenshot_dir / f"{name}.png").write_bytes(base64.b64decode(b64))
    logger.info(f"| GoogleLensSearch screenshot: {name}.png")


async def _run_lens_search(image_path: Path, text: str, chromium_path: str, screenshot_dir: Optional[str] = None) -> str:
    """Drive a headless browser through Google Lens and return the results as markdown.

    Launches a Chromium session, uploads `image_path` to lens.google.com, optionally
    refines the search with `text`, waits for the results page, then strips the page to
    its main content and converts it to cleaned markdown (nav/boilerplate/images removed).

    Args:
        image_path: Local image file to search with.
        text: Optional text query to add to the visual search; skipped if empty.
        chromium_path: Path to the Chromium executable to run.
        screenshot_dir: Optional directory for step-by-step debug screenshots.

    Returns:
        The Lens results page rendered as cleaned markdown text.

    Raises:
        RuntimeError: If a CAPTCHA is triggered or the results page never loads.
    """
    from browser_use.browser.session import BrowserSession
    from markitdown import MarkItDown

    ss_dir = Path(screenshot_dir) if screenshot_dir else None

    session = BrowserSession(
        executable_path=chromium_path,
        headless=True,
        is_local=True,
        enable_default_extensions=False,
        chromium_sandbox=False,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        args=[
            "--lang=en-US",
            "--accept-lang=en-US,en;q=0.9",
        ],
    )
    await session.start()

    try:
        page = await session.new_page("about:blank")

        # 1. Open Google Lens upload page
        await page.goto("https://lens.google.com/upload")
        await _wait_ms(page, 2000)
        await _save_screenshot(page, ss_dir, "01_lens_upload_page")

        # Dismiss cookie consent dialog if present
        await page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                if (['Accept all', 'I agree', 'Accept'].some(l => btn.textContent.trim().includes(l))) {
                    btn.click(); break;
                }
            }
        }""")
        await _wait_ms(page, 800)

        # 2. Upload image
        await _save_screenshot(page, ss_dir, "02_before_upload")
        await _upload_file(page, str(image_path))

        # 3. Wait for results page
        result_page = None
        for i in range(60):
            await asyncio.sleep(0.5)
            try:
                url = await page.get_url()
            except Exception:
                continue
            if "search" in url and "upload" not in url and "sorry" not in url:
                result_page = page
                break
            if "sorry" in url:
                await _save_screenshot(page, ss_dir, "captcha")
                raise RuntimeError("Google CAPTCHA triggered")
        else:
            await _save_screenshot(page, ss_dir, "timeout")
            raise RuntimeError("Timed out waiting for Google Lens results page")

        await _wait_ms(result_page, 3000)
        await _save_screenshot(result_page, ss_dir, "03_result_page")

        # 4. Enter text query if provided
        if text:
            await _enter_search_text(result_page, text)
            await _save_screenshot(result_page, ss_dir, "04_after_text_input")

        # 5. Convert page to markdown via temp file
        await asyncio.sleep(2)
        await _save_screenshot(result_page, ss_dir, "05_final")
        # Extract only the main content area, stripping nav/header/footer/script/style
        html = await result_page.evaluate("""() => {
            const clone = document.body.cloneNode(true);
            // Remove noise elements
            for (const sel of [
                'script', 'style', 'nav', 'header', 'footer',
                '[role=navigation]', '[role=banner]',
                '#sfcnt', '#botstuff', '#footcnt', '#hdtb', '#top_nav',
                '.action-menu', '.hdtb-mitem', '.qs-ic',
                // time filter toolbar
                '#tl_loading', '.hdtb-td-h', '[data-hveid]#tvcap',
                // feedback dropdown (Delete / See more)
                'g-dropdown-menu', 'g-menu',
            ]) {
                clone.querySelectorAll(sel).forEach(el => el.remove());
            }
            // Remove the search tools / time-filter section
            const toolsSection = clone.querySelector('#hdtb-tls, .hdtbItem');
            if (toolsSection) toolsSection.remove();
            return clone.innerHTML;
        }""")

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
            f.write(html)
            tmp_path = Path(f.name)

        try:
            md = MarkItDown().convert(tmp_path).text_content
        finally:
            tmp_path.unlink(missing_ok=True)

        # Strip all image tags (base64, tbn, gstatic, empty)
        md = re.sub(r'!\[.*?\]\([^)]*\)', '', md)
        # Strip JS-redirect boilerplate at the top
        md = re.sub(r'^.*?Please click.*?\n', '', md, flags=re.DOTALL)
        # Strip accessibility/nav boilerplate lines
        boilerplate = [
            r'Skip to main content.*?\n',
            r'Accessibility (help|feedback).*?\n',
            r'Press / to jump.*?\n',
            r'Choose what you.*?\n',
            r'Report inappropriate.*?\n',
            r'Quick Settings\n',
            r'Ctrl\+Shift\+X.*?\n',
            r'About \d[\d,]*,\d+ results.*?\n',
        ]
        for pattern in boilerplate:
            md = re.sub(pattern, '', md)
        # Strip feedback dropdown noise line by line
        lines = md.splitlines()
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped in ('- Delete', '- ---', 'See more', '---'):
                continue
            clean_lines.append(line)
        md = '\n'.join(clean_lines)
        # Collapse excessive blank lines
        md = re.sub(r'\n{3,}', '\n\n', md).strip()

        return md

    finally:
        await session.stop()


async def _wait_ms(page, ms: int):
    """Pause `ms` milliseconds in the page's own timeline via an in-page setTimeout."""
    await page.evaluate(f"() => new Promise(r => setTimeout(r, {ms}))")


async def _upload_file(page, file_path: str):
    """Upload a local image to the Google Lens page via the CDP DOM protocol.

    Clicks the "upload a file" control, locates the hidden file input, and injects
    `file_path` with ``DOM.setFileInputFiles`` (avoids a native file picker).

    Args:
        page: The active browser page.
        file_path: Absolute path to the image to upload.

    Raises:
        RuntimeError: If the upload trigger or file input element cannot be found.
    """
    session_id = await page._ensure_session()
    client = page._client

    elements = await page.get_elements_by_css_selector('span[jsname="tAPGc"]')
    if not elements:
        elements = await page.get_elements_by_css_selector('span.DV7the')
    if not elements:
        raise RuntimeError("Could not find 'upload a file' element")

    await elements[0].click()
    await asyncio.sleep(1.5)

    doc = await client.send.DOM.getDocument(session_id=session_id)
    root_id = doc["root"]["nodeId"]

    for selector in ['input[name="encoded_image"]', 'input[type=file][accept*="image"]', 'input[type=file]']:
        query = await client.send.DOM.querySelector(
            {"nodeId": root_id, "selector": selector},
            session_id=session_id,
        )
        if query["nodeId"]:
            break
    else:
        raise RuntimeError("Could not find input[type=file]")

    desc = await client.send.DOM.describeNode(
        {"nodeId": query["nodeId"]}, session_id=session_id
    )
    backend_node_id = desc["node"]["backendNodeId"]

    await client.send.DOM.setFileInputFiles(
        {"files": [file_path], "backendNodeId": backend_node_id},
        session_id=session_id,
    )


async def _enter_search_text(page, text: str):
    """Type a refinement query into the Lens results search box and submit it.

    Tries a series of candidate selectors for the search field, fills the first
    match, and prefers clicking the Search button (to preserve image context),
    falling back to submitting the form. Returns without action if no field matches.
    """
    selectors = [
        "textarea[aria-label='Add to your search']",
        "input[aria-label='Add to your search']",
        "textarea[placeholder*='Add']",
        "textarea.gLFyf",
        "input.gLFyf",
        "textarea",
    ]
    for sel in selectors:
        elements = await page.get_elements_by_css_selector(sel)
        if elements:
            await elements[0].click()
            await elements[0].fill(text)
            await _wait_ms(page, 800)
            # Prefer clicking the search button to preserve image context
            submitted = False
            for btn_sel in ['button[aria-label="Search"]', 'button[type="submit"]']:
                btns = await page.get_elements_by_css_selector(btn_sel)
                if btns:
                    await btns[0].click()
                    submitted = True
                    break
            if not submitted:
                # fallback: form.submit() — loses image context but still works
                try:
                    await page.evaluate("""() => {
                        const form = document.querySelector('form');
                        if (form) form.submit();
                    }""")
                except Exception:
                    pass
            await asyncio.sleep(4)
            return
