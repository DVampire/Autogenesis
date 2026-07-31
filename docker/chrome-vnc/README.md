# chrome-vnc — headful Chrome with a live noVNC view

Extends `opensandbox/chrome:latest` (the image the browser environment already
drives over CDP) with a virtual display and a VNC bridge, so the frontend can
watch the agent browse in real time over noVNC while Playwright keeps driving
the page over the DevTools protocol.

## What it adds
- **Xvfb** — a virtual X display (`:99`) so Chrome can run **headful**.
- **x11vnc** — a VNC (RFB) server on the display (`:5900`).
- **websockify + noVNC** — bridges RFB to a WebSocket on `:6080`; this is what
  the browser's noVNC client connects to.
- Chrome runs **headful** with `--remote-debugging-port=9222` (CDP unchanged).

## Ports
| Port | Purpose |
| --- | --- |
| 9222 | Chrome DevTools (CDP) — Playwright `connect_over_cdp` |
| 5900 | raw VNC (internal) |
| 6080 | websockify (RFB over WebSocket) — the noVNC endpoint |

## Build
The browser environment auto-builds this image when it is missing (see
`sandbox/default/chrome_vnc.py`). To build it manually:

```bash
docker build -t autogenesis/chrome-vnc:latest docker/chrome-vnc/
```

OpenSandbox runs as a local daemon over local Docker, so a locally-built,
locally-tagged image is usable without pushing to a registry.

## How the live view reaches the frontend
1. The browser environment runs on this image (headful) via the `chrome-vnc`
   sandbox, which exposes port **6080** through the OpenSandbox proxy.
2. `BrowserEnvironment.live_view()` returns an `EnvironmentView(kind="vnc", url=<websockify ws>)`.
3. `environment_manager` announces it on the `environment_stream` bus; the
   Gateway republishes it as an `environment.view` event to the active session.
4. The frontend renders a noVNC canvas in the conversation, connected straight
   to the websockify endpoint — pixels never pass through the agent or gateway.

## Notes / assumptions
- Assumes the base image is Debian/Ubuntu-based with `apt-get`. Adjust the
  package manager if the base changes.
- The Chrome binary is auto-detected (`google-chrome` / `chromium` / …).
- No VNC password by default (`x11vnc -nopw`); the stream is only reachable
  through the sandbox proxy. Add a password + `EnvironmentView.password` if you
  expose it more widely.
