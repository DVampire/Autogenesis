---
name: artifact_renderer
description: Render self-contained HTML in an isolated browser and screenshot it.
version: 1.0.0
type: worker
---

<environment_artifact_renderer>

## State
A sandboxed headless Chrome that renders self-contained HTML and returns a screenshot. The framework's local analogue of claude.ai Artifacts: generate HTML → render here → look at the screenshot → fix. Pairs with the artifact_design_skill.

## Vision
This environment has vision: `render_artifact` returns a base64 PNG screenshot of the rendered page. Inspect it visually to verify layout, spacing, and colors before iterating.

## Actions

### render_artifact
Render self-contained HTML in an isolated browser and return a screenshot.

Parameters:
- html (str): The self-contained HTML to render. A strict CSP is injected, so inline ALL CSS/JS and embed assets as data: URIs — external stylesheets, scripts, remote images/fonts, and fetch/XHR/WebSocket calls are blocked and will not load.
- wait_ms (int, optional): Extra wait after load settles, in milliseconds (default 800).
- validate_csp (bool, optional): Scan for resources the CSP would block and warn about them (default true).

Returns: a screenshot (base64 PNG), the viewport, and any detected CSP violations.

## Interaction
Input format: a JSON string with action-specific parameters.
Example: {"name": "render_artifact", "args": {"html": "<!doctype html><html><head><style>body{font-family:sans-serif}</style></head><body><h1>Hello</h1></body></html>"}}

</environment_artifact_renderer>
