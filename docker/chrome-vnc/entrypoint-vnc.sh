#!/usr/bin/env bash
# Start a virtual display, a VNC server + websockify bridge, then headful Chrome
# with the DevTools port open. Chrome runs in the FOREGROUND (PID 1) so the
# container's lifetime tracks the browser; the rest run as background daemons.
set -euo pipefail

SCREEN_GEOMETRY="${SCREEN_GEOMETRY:-1280x800x24}"
DISPLAY_NUM="${DISPLAY_NUM:-:99}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
CDP_PORT="${CDP_PORT:-9222}"
export DISPLAY="${DISPLAY_NUM}"

# 1) Virtual display.
Xvfb "${DISPLAY_NUM}" -screen 0 "${SCREEN_GEOMETRY}" -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 30); do xdpyinfo -display "${DISPLAY_NUM}" >/dev/null 2>&1 && break; sleep 0.2; done

# 2) Lightweight window manager so Chrome shows a normal framed window.
fluxbox >/tmp/fluxbox.log 2>&1 &

# 3) VNC server on the display, and the websockify bridge that noVNC connects to.
x11vnc -display "${DISPLAY_NUM}" -forever -shared -nopw -rfbport "${VNC_PORT}" -quiet >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${VNC_PORT}" >/tmp/websockify.log 2>&1 &

# 4) Locate the Chrome/Chromium binary shipped in the base image.
CHROME_BIN=""
for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "${candidate}" >/dev/null 2>&1; then CHROME_BIN="${candidate}"; break; fi
done
if [ -z "${CHROME_BIN}" ]; then echo "No Chrome/Chromium binary found in image" >&2; exit 1; fi

# 5) Headful Chrome with remote debugging reachable from the sandbox proxy.
CHROME_ARGS=(
    --no-sandbox
    --no-first-run
    --disable-gpu
    --remote-debugging-address=0.0.0.0
    --remote-debugging-port="${CDP_PORT}"
    --window-position=0,0
    --window-size=1280,800
    --start-maximized
)
# Only append extra args when actually set — an unset var must NOT expand to a
# stray empty "" argument, which Chrome would treat as a blank URL to open.
if [ -n "${CHROME_EXTRA_ARGS:-}" ]; then
    # shellcheck disable=SC2206  # word-splitting is intended for multiple flags
    CHROME_ARGS+=(${CHROME_EXTRA_ARGS})
fi
exec "${CHROME_BIN}" "${CHROME_ARGS[@]}" about:blank
