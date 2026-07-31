#!/usr/bin/env bash
# $BROWSER for the IDE container: make loopback OAuth work from a remote browser.
#
# A CLI doing the standard OAuth loopback flow (RFC 8252) binds
# localhost:<random port> inside this container and hands the provider
# redirect_uri=http://localhost:<port>/callback. That assumes the browser runs on
# the same host as the CLI. Here it does not — the browser is on the user's
# machine, where nothing is listening on that port, so the callback dies with
# ERR_CONNECTION_REFUSED after a perfectly good authorization.
#
# The IDE already exposes every container port to that browser as
# <port>-<session>.ide.localhost, so the listener IS reachable — just not at the
# name the CLI chose. This shim rewrites the redirect_uri to the reachable name
# before the URL ever reaches the browser.
#
# Generic by construction: it keys off the redirect_uri query parameter, which is
# part of OAuth, not off any particular tool.
set -euo pipefail

url="${1:-}"
[[ -z "$url" ]] && { echo "usage: $(basename "$0") <url>" >&2; exit 1; }

rewritten=$(
    IDE_SESSION_ID="${IDE_SESSION_ID:-}" IDE_UI_ORIGIN="${IDE_UI_ORIGIN:-}" \
    "${OPENVSCODE_SERVER_ROOT}/node" -e '
const [,, raw] = process.argv;
const session = process.env.IDE_SESSION_ID || "";
const origin  = process.env.IDE_UI_ORIGIN  || "";   // e.g. "localhost:5173"
try {
  const url = new URL(raw);
  const target = url.searchParams.get("redirect_uri");
  if (!session || !origin || !target) { console.log(raw); process.exit(0); }
  const cb = new URL(target);
  // Only loopback redirects are broken; leave anything else untouched.
  const loopback = cb.hostname === "localhost" || cb.hostname === "127.0.0.1" || cb.hostname === "[::1]";
  if (!loopback || !cb.port) { console.log(raw); process.exit(0); }
  const [, uiPort = "5173"] = origin.split(":");
  cb.protocol = "http:";
  cb.host = `${cb.port}-${session}.ide.localhost:${uiPort}`;
  url.searchParams.set("redirect_uri", cb.toString());
  console.log(url.toString());
} catch { console.log(raw); }
' "$url"
)

if [[ "$rewritten" != "$url" ]]; then
    echo "| 🔗 Rewrote the OAuth callback so it can reach this container." >&2
fi

# Hand it to the user's browser. openvscode-server's remote CLI asks the
# connected browser tab to open the URL; if that is unavailable (no attached
# client) fall back to printing it — the integrated terminal makes URLs
# clickable, so it stays one click either way.
if [[ -x "${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/openvscode-server" ]] \
   && "${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/openvscode-server" --openExternal "$rewritten" 2>/dev/null; then
    exit 0
fi

echo "" >&2
echo "Open this URL to continue signing in:" >&2
echo "  $rewritten" >&2
echo "" >&2
