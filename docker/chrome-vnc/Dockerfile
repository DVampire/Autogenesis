# Headful Chrome + VNC, on top of the OpenSandbox Chrome image the browser
# environment already uses. Adds a virtual display (Xvfb), a VNC server (x11vnc),
# and a websockify bridge serving noVNC on 6080 — so the frontend can watch the
# live browser over a WebSocket (noVNC), while Playwright still drives it via CDP.
#
# Ports:
#   9222  Chrome DevTools (CDP)         — driven by Playwright (connect_over_cdp)
#   5900  raw VNC (RFB)                 — internal
#   6080  websockify (RFB over WebSocket) — what noVNC in the browser connects to
#
# Build (the browser env auto-builds this when missing; or run it yourself):
#   docker build -t autogenesis/chrome-vnc:latest docker/chrome-vnc/
FROM opensandbox/chrome:latest

USER root

# Xvfb (virtual display), a minimal WM, x11vnc (RFB server), and noVNC+websockify.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        fluxbox \
        x11vnc \
        novnc \
        websockify \
        procps \
    && rm -rf /var/lib/apt/lists/*

# noVNC ships its client under /usr/share/novnc; expose vnc.html as the index so
# a plain http open of the endpoint also works, not only the RFB WebSocket.
RUN if [ -f /usr/share/novnc/vnc.html ] && [ ! -e /usr/share/novnc/index.html ]; then \
        ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html; \
    fi

COPY entrypoint-vnc.sh /usr/local/bin/entrypoint-vnc
RUN chmod +x /usr/local/bin/entrypoint-vnc

EXPOSE 9222 5900 6080
ENTRYPOINT ["/usr/local/bin/entrypoint-vnc"]
