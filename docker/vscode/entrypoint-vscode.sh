#!/usr/bin/env bash
# Launch openvscode-server for one session.
#
# OpenSandbox ignores the image ENTRYPOINT and passes its own command, so
# VscodeSandbox hands this script over explicitly as the entrypoint (the same
# reason the chrome-vnc sandbox passes /usr/local/bin/entrypoint-vnc).
#
# Extensions and user data live on MOUNTED directories keyed by OWNER, not by
# session, so installed plugins and settings survive across sessions even though
# the container itself is per-session.
set -euo pipefail

EXT_DIR="${IDE_EXTENSIONS_DIR:-/ide/extensions}"
DATA_DIR="${IDE_USER_DATA_DIR:-/ide/user-data}"
FOLDER="${IDE_FOLDER:-/workspace}"
PORT="${IDE_PORT:-3000}"
# Sub-path this editor is served under, e.g. /ide/<session>. openvscode-server
# then emits its absolute asset paths already prefixed, which is what lets the
# UI host the IDE on its OWN origin instead of a per-session *.ide.localhost
# name that only resolves when the browser sits on the server. Empty = root.
BASE_PATH="${IDE_BASE_PATH:-}"
# Coding agents, installed on first use. Both ship their CLI as a bundled
# native binary, so neither needs npm — which matters where registry egress is
# restricted. Set to "" to opt out.
DEFAULT_EXTENSIONS="${IDE_DEFAULT_EXTENSIONS-anthropic.claude-code openai.chatgpt}"

mkdir -p "$EXT_DIR" "$DATA_DIR" "$DATA_DIR/User" "$DATA_DIR/server" "$FOLDER"

# Any CLI that opens a browser goes through the shim, which repoints a loopback
# OAuth callback at this container's forwarded origin. xdg-open is aliased too,
# since some tools reach for it directly instead of honouring $BROWSER.
export BROWSER=/usr/local/bin/ide-open

# The image is built on autogenesis/base, so the agent's conda environment is
# right here — put it first on PATH so the integrated terminal opens in the same
# Python the agent uses, not a bare system one.
export PATH="/opt/conda/bin:${PATH}"
ln -sf /usr/local/bin/ide-open /usr/local/bin/xdg-open 2>/dev/null || true

# Seed user settings on first run only — the directory is mounted per owner, so
# after this the file belongs to the user and is never rewritten.
#
# Workspace trust is off because the mounted folder is the user's OWN session
# workspace, not third-party code they just opened. Left on, VS Code greets
# every new session with a modal and starts restricted, which disables the
# terminal and the extensions we just installed — the prompt protects against a
# threat that does not exist here while breaking the thing outright.
SETTINGS="$DATA_DIR/User/settings.json"
if [ ! -f "$SETTINGS" ]; then
    cat > "$SETTINGS" <<'JSON'
{
  "security.workspace.trust.enabled": false,
  "telemetry.telemetryLevel": "off",
  "python.defaultInterpreterPath": "/opt/conda/bin/python",
  "terminal.integrated.env.linux": { "PATH": "/opt/conda/bin:${env:PATH}" }
}
JSON
fi

# Install the defaults before the server starts, so they are present the moment
# the user connects rather than appearing after a reload. The extensions
# directory is mounted per OWNER, so this download happens once and every later
# session skips straight past it.
for extension in $DEFAULT_EXTENSIONS; do
    # Installed copies are directories named "<id>-<version>-<platform>".
    if compgen -G "$EXT_DIR/${extension}-*" > /dev/null; then
        continue
    fi
    echo "| 📦 Installing default extension: ${extension}"
    # Never fatal: a registry hiccup should cost you an extension, not the IDE.
    "${OPENVSCODE_SERVER_ROOT}/bin/openvscode-server" \
        --extensions-dir "$EXT_DIR" \
        --install-extension "$extension" \
        || echo "| ⚠️ Could not install ${extension}; continuing without it"
done

# --without-connection-token: the port is bound to loopback by the opensandbox
# proxy and only reachable through the gateway-authorised route, so VS Code's
# own token would be a second, redundant secret in every asset URL.
BASE_PATH_ARG=()
[ -n "$BASE_PATH" ] && BASE_PATH_ARG=(--server-base-path "$BASE_PATH")

exec "${OPENVSCODE_SERVER_ROOT}/bin/openvscode-server" \
    --host 0.0.0.0 \
    --port "$PORT" \
    "${BASE_PATH_ARG[@]}" \
    --without-connection-token \
    --telemetry-level off \
    --extensions-dir "$EXT_DIR" \
    --user-data-dir "$DATA_DIR" \
    --server-data-dir "$DATA_DIR/server"
