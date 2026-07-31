#!/usr/bin/env bash
set -euo pipefail

# Start the Autogenesis backend Gateway AND the browser UI together — both inside
# the base sandbox (Model X). This is the command you hand to run-in-sandbox.sh:
#
#   scripts/run-in-sandbox.sh -- scripts/serve-ui.sh
#
# The sandbox runs with --network host, so both servers bind the container's
# loopback, which IS the host loopback. From the host browser:
#   frontend  http://127.0.0.1:5173   (the Vite dev server, serves the SPA)
#   backend   ws://127.0.0.1:9876/ws  (the Gateway the SPA connects to)
#
# Ports are overridable via GATEWAY_PORT / UI_PORT. When unset, they default to
# the framework's well-known ports from the port registry (autogenesis.port), so
# there is one source of truth instead of scattered literals. Extra args are
# forwarded to `autogenesis serve` (e.g. --token, --allow-origin).

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_PORT="${GATEWAY_PORT:-$(python -c 'from autogenesis.port import GATEWAY; print(GATEWAY)')}"
UI_PORT="${UI_PORT:-$(python -c 'from autogenesis.port import UI; print(UI)')}"

# Record the UI port in the PortManager (persisted to ports.json) so it is
# discoverable alongside the Gateway (which `autogenesis serve` registers
# itself). Both are fixed host ports — the single port a remote user forwards.
python -c "from autogenesis.port import port_manager; port_manager.register('ui', ${UI_PORT}, kind='host', override=True)" || true

GW_PID=""
UI_PID=""
CHOWN_PID=""
# Give the Gateway time to shut down properly: it destroys the per-session IDE
# containers there. Signalling it and leaving immediately orphaned every one of
# them — they outlived the run, and enough of them exhausted the host's file
# descriptors (openvscode-server's file watchers gave EMFILE and the editor
# never finished loading).
GW_STOP_TIMEOUT="${GW_STOP_TIMEOUT:-25}"
cleanup() {
  trap - EXIT INT TERM   # a second Ctrl-C should not re-enter this
  if [[ -n "${GW_PID}" ]] && kill -0 "${GW_PID}" 2>/dev/null; then
    kill "${GW_PID}" 2>/dev/null || true
    for _ in $(seq "${GW_STOP_TIMEOUT}"); do
      kill -0 "${GW_PID}" 2>/dev/null || break
      sleep 1
    done
    kill -9 "${GW_PID}" 2>/dev/null || true
  fi
  [[ -n "${UI_PID}" ]] && kill "${UI_PID}" 2>/dev/null || true
  [[ -n "${CHOWN_PID}" ]] && kill "${CHOWN_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# The container runs as root (needed for pip-install into conda + the Docker
# socket to spawn peer containers — see entrypoint). The entrypoint only chowns
# output/ back to the host owner on EXIT, but the UI server is long-lived, so
# without this loop the host user could never delete output/ while it runs.
# Periodically hand root-created output files back to the host project owner.
HOST_OWNER="$(stat -c '%u:%g' "${REPO_ROOT}" 2>/dev/null || echo '')"
if [[ -n "${HOST_OWNER}" && "${HOST_OWNER}" != "0:0" ]]; then
  ( while true; do
      sleep 20
      find "${REPO_ROOT}/output" -uid 0 -exec chown "${HOST_OWNER}" {} + 2>/dev/null || true
    done ) &
  CHOWN_PID=$!
fi

echo "Autogenesis — serve UI in sandbox (Model X)"
echo "  backend  : ws://127.0.0.1:${GATEWAY_PORT}/ws"
echo "  frontend : http://127.0.0.1:${UI_PORT}"

# Backend Gateway in the background. It is the framework itself, so it must run
# under Model X (here, inside this container). Extra args ($@) pass straight through.
autogenesis serve --transport websocket --host 127.0.0.1 --port "${GATEWAY_PORT}" "$@" &
GW_PID=$!

# Frontend deps: the repo is bind-mounted, so node_modules is absent on the first
# launch. Install once (persists on the host via the mount); skip if already present.
cd "${REPO_ROOT}/frontend"
if [[ ! -d node_modules ]]; then
  echo "| 📦 Installing frontend deps (first launch only)…"
  npm install
fi

# Raise the open-file limit: Vite's file watcher (chokidar) opens many FDs, and
# the repo is large, so the container's default soft limit (often 1024) trips
# EMFILE. Bump toward the hard limit; fall back gracefully if not permitted.
ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn 2>/dev/null || echo 8192)" 2>/dev/null || true

# Vite in the background, then wait. Two shell details decide whether the
# cleanup above ever runs: `exec` would replace this shell (and its trap) with
# npm, and a *foreground* command makes bash defer every trap until it returns —
# either way SIGTERM would be queued forever while the Gateway is killed
# unclean, orphaning the IDE containers it started. Only `wait` is interruptible.
npm run dev -- --port "${UI_PORT}" &
UI_PID=$!
wait "${UI_PID}"
