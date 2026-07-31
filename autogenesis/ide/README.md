---
name: ide
description: "Full VS Code (openvscode-server) in the browser, one container per gateway session, editing the same workspace the agent edits. Human-facing: not an agent capability."
version: 1.0.0
type: module
category: interface
requirements: []
metadata:
  document_version: 1
---
# IDE

A real **VS Code in the browser** — extensions, integrated terminal, search,
git — editing the *same* workspace files the agent works on. One container per
gateway session, started on demand and reaped when idle.

Like the [canvas](../canvas/README.md), this is **human-facing**: the agent
never calls into it, and the IDE is not registered as a capability the meta
agent can see.

## Why it is served under a path on the UI's own origin

VS Code emits **absolute** asset paths (`/stable-<commit>/static/...`), so a
sub-path works only if the server knows about it. openvscode-server does:
`--server-base-path /ide/<session>` prefixes every URL it emits, so both sides
agree and nothing has to be rewritten.

```
<ui origin>/                 → Autogenesis SPA
<ui origin>/ide/<session>/   → that session's IDE
```

The UI's own origin is the one address every deployment agrees on — whatever the
browser reached the app at works, including through a tunnel or a reverse proxy.

> This used to be a per-session **host** instead (`<session>.ide.localhost`).
> That name is resolved by the **browser**, where `*.localhost` is loopback — so
> it only ever worked with the browser running on the machine serving the UI.
> Reached through a tunnel, the iframe pointed at the user's own laptop and came
> up blank. A wildcard host cannot be fixed by forwarding either: it needs DNS
> and a certificate per session.

## The chain

```
browser  <ui origin>/ide/<sid>/stable-…/static/x.js
   │  vite plugin matches the path, prepends the proxy prefix
   ▼
gateway-resolved upstream  127.0.0.1:<ephemeral>/proxy/3000/ide/<sid>/stable-…/static/x.js
   │  the opensandbox proxy strips /proxy/3000
   ▼
openvscode-server :3000    /ide/<sid>/stable-…/static/x.js   ← its own base path
```

Each hop strips exactly the prefix it added, so VS Code is never aware it is
proxied and needs no patching. The workbench WebSocket rides the same path.

## Port forwarding

Other ports in the session's container get a **host** rather than a path: a dev
server or an OAuth callback listener does not know it is proxied and has no base
path to configure, so only a root of its own keeps its absolute URLs working.

```
<port>-<session>.ide.localhost:5173   → any other port in the same container
```

Same caveat as the note above — `*.localhost` is loopback on the *browser's*
machine, so this form needs a browser on the server, or the UI port forwarded to
where the browser runs (`ssh -L 5173:127.0.0.1:5173 <host>`).

A dev server, a preview, a notebook, an OAuth callback listener — all reachable
with no per-tool support. Ports resolve on first use (exposing one is a round
trip to opensandbox) and are cached for the container's life.

**What this cannot do**, and why it is not a gap we can close: it exposes a
container port at a *URL*, not at `localhost:<port>` **on your machine**. Only a
native process on your machine can bind your loopback — that is exactly how VS
Code Remote-SSH does it, and a browser tab cannot bind ports at all. Codespaces
and Gitpod hand out URLs for the same reason.

So a tool whose OAuth `redirect_uri` is hard-coded to `localhost:<random port>`
still cannot complete its browser login in here: the browser resolves that on
your machine, where nothing is listening. That is a property of the OAuth
public-client flow in any remote environment, not of this setup — which is why
the remote-friendly alternatives exist and are the supported path:

| Tool | Callback-free sign-in |
|---|---|
| Claude Code | `CLAUDE_CODE_OAUTH_TOKEN` (mint once elsewhere with `claude setup-token`) — forwarded by `ide_manager` |
| Codex | `codex login --device-auth` (RFC 8628 device code) |

## Lifecycle

Lazy start on first open; a heartbeat plus every proxied request refresh the
idle clock; a reaper destroys containers idle past `idle_timeout_seconds`
(default 30 min). The gateway has no `session.close`, so **time** — not session
teardown — is what frees these. `max_instances` caps concurrent IDEs and evicts
the least recently used.

## State

| What | Scope | Why |
|---|---|---|
| `/workspace` | **per session** | the files the agent edits — same bytes, no copy |
| extensions | **per owner** | installed plugins survive new sessions |
| user data | **per owner** | settings and keybindings persist |
| `$HOME` | **per owner** | `~/.codex` and `~/.claude` live here, so an agent sign-in outlives the container |

Per-session containers with per-owner plugin state: a new session is isolated
but never makes you reinstall your extensions.

## Boundaries

- The container **never mounts the Docker socket**, so its terminal cannot reach
  the host daemon.
- That terminal is still a real shell inside the container, and it does not pass
  through the permission manager — its reach is the container plus the mounts
  above.
- Extensions come from **Open VSX**; Microsoft-licensed ones (Pylance, official
  C#/Remote packs) are not published there. **Claude Code**
  (`anthropic.claude-code`) and **Codex** (`openai.chatgpt`) are, and are
  installed on first use — each bundles its own CLI, so neither needs npm. See
  [`docker/vscode/README.md`](../../docker/vscode/README.md).

## Pieces

| Piece | Where |
|---|---|
| Image | [`docker/vscode/`](../../docker/vscode/) |
| Container handle | `autogenesis/sandbox/default/vscode.py` (`VscodeSandbox`) |
| Lifecycle | `server.py` (`ide_manager`) |
| Commands + resolve | `autogenesis/gateway/` (`ide.start` / `ide.status` / `ide.stop`) |
| Host routing | `frontend/vite.config.ts` |
| View | `frontend/src/ide/` |
