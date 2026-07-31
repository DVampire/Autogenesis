# vscode — full VS Code in the browser, per session

Built on `autogenesis/base` (miniconda3 + the installed project) with
openvscode-server copied in from `gitpod/openvscode-server`, so the editor and
the agent share one environment. One container per gateway session; the frontend
embeds it in an iframe.

## What it adds
- **root user** — the stock image runs as uid 1000, but workspace files belong
  to the host user. Running as root keeps them writable; `scripts/serve-ui.sh`
  already chowns `output/` back to the host owner periodically.
- **the agent's own environment** — the image is built on `autogenesis/base`,
  so the integrated terminal has the same miniconda3 at `/opt/conda` and the
  same project the agent runs with. `PATH` puts it first and
  `python.defaultInterpreterPath` points at it, so a terminal opens straight
  into the project's Python. Layers are shared with a base image already on the
  host, so this costs ~200MB rather than a second ~10GB copy of conda.
- **openvscode-server, copied from the upstream image** rather than downloaded,
  so the build needs no network beyond the two base pulls. It ships its own
  node, so nothing else is required.
- **`ide-open`** wired up as `$BROWSER` (and `xdg-open`): rewrites a loopback
  OAuth `redirect_uri` onto this container's forwarded origin, so a browser
  sign-in started in the terminal can actually return here.
- **entrypoint-vscode** — starts openvscode-server on `:3000` against the
  mounted directories below. OpenSandbox ignores the image ENTRYPOINT, so
  `VscodeSandbox` passes this script explicitly (same as chrome-vnc).

## Mounts
| Container path | Host source | Scope |
|---|---|---|
| `/workspace` | `session.sandbox.workspace_root` | **per session** — the same files the agent edits |
| `/ide/extensions` | `output/<owner>/state/ide/extensions` | **per owner** — installed plugins survive new sessions |
| `/ide/user-data` | `output/<owner>/state/ide/user-data` | **per owner** — settings and keybindings |
| `/home/workspace` | `output/<owner>/state/ide/home` | **per owner** — `$HOME`, so `~/.codex` and `~/.claude` logins survive a reaped container. Empty in the image, so nothing is shadowed. |

The container never mounts the Docker socket, so its integrated terminal cannot
reach the host daemon.

## Ports
- `3000` — openvscode-server: HTTP **and** the workbench WebSocket, same port.

Served under `/ide/<session>/` on the UI's own origin. `entrypoint-vscode` passes
that as `--server-base-path` (from `IDE_BASE_PATH`), so VS Code's absolute asset
paths carry the prefix and resolve untouched. See
[`autogenesis/ide/README.md`](../../autogenesis/ide/README.md) for the full
routing chain.

## Extensions
openvscode-server uses the **Open VSX** registry, not the Microsoft
Marketplace. Microsoft-licensed extensions (Pylance, the official C# and Remote
packs) are not published there and cannot be installed.

Two coding agents are installed on first use, both published on Open VSX:

| Extension | Ships |
|---|---|
| `anthropic.claude-code` — Claude Code for VS Code | its `claude` CLI as a bundled native binary |
| `openai.chatgpt` — Codex, OpenAI's coding agent | its host binary under `bin/` |

Because each bundles its own CLI, neither needs npm — which matters on hosts
where registry egress is restricted. They land on the per-owner extensions
mount, so the (few hundred MB) download happens once and every later session
skips it. Override the list with `IDE_DEFAULT_EXTENSIONS` (space-separated), or
set it empty to install nothing.

## Build
Built automatically on first use by `VscodeSandbox._ensure_image()`, or:

```bash
docker build -t autogenesis/vscode:latest docker/vscode/
```
