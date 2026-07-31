---
name: browser_environment
description: Playwright browser environment for web automation.
version: 1.0.0
type: worker
---

<environment_browser>

## State
The state of the browser environment: the current URL, page title, open tabs, and a list of interactive elements. When set-of-marks (SoM) is on, the state screenshot draws numbered boxes over interactive elements that match the elements list.

## Vision
This environment has vision: each observation returns a screenshot of the current page (optionally annotated with numbered element boxes and the last action's cursor/scroll/drag overlay). Use the coordinates from the elements list / boxes to target actions.

## Actions

### click
Click at specified coordinates on the page.
- x (int), y (int): pixel coordinates.
- button (str, optional): "left" (default), "right", or "middle".

### double_click
Double-click at specified coordinates.
- x (int), y (int): pixel coordinates.

### scroll
Scroll at specified coordinates with given offsets.
- x (int), y (int): where to scroll.
- scroll_x (int), scroll_y (int): horizontal/vertical scroll offsets.

### type
Type text at the current cursor position.
- text (str): the text to type.

### wait
Wait for a period before the next observation.
- ms (int, optional): milliseconds to wait (default 1000).

### move
Move the mouse to specified coordinates.
- x (int), y (int): pixel coordinates.

### keypress
Press specified keys.
- keys (list[str]): keys to press, e.g. ["Enter"] or ["Control", "a"].

### drag
Drag the mouse along a path.
- path (list[[int, int]]): ordered list of [x, y] points.

### goto
Navigate the browser to a URL. Accepts a full URL (https://...) or a bare domain. Use this to open a link found via `search`.
- url (str): the destination URL.

### search
Search the web and get a ranked list of results (title, URL, description) via the Firecrawl API. Runs server-side (not blocked by local IP/CAPTCHA), so prefer it over navigating to a search engine. Discover pages here, then open one with `goto`.
- query (str): the search query.
- num_results (int, optional): number of results (default 5).

### command
Run a Playwright Python snippet with `page` (current Page) and `context` (BrowserContext) in scope. Use as a fallback when coordinate-based actions fail (element not clickable/hidden/moving) or to read structured data. The code runs inside an async function: use `await` directly and `return` to send a value back. Timeout: 30s.
- code (str): the Playwright snippet, e.g. `await page.locator("text=Login").click()` or `return await page.locator(".price").all_inner_texts()`.

## Interaction
Input format: a JSON string with action-specific parameters.
Example: {"name": "goto", "args": {"url": "https://example.com"}}
Example: {"name": "click", "args": {"x": 480, "y": 320, "button": "left"}}

</environment_browser>
