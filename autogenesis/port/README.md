---
name: port
description: "Central port registry — names the framework's well-known default ports and hands out / records host ports, persisted to output/.runtime so bindings are de-conflicted and discoverable."
version: 1.0.0
type: module
category: port
requirements: []
metadata: {}
---
# Port

Central port registry. Replaces ad-hoc port literals and one-off free-port
picking with:

- **Named defaults** (`server.py`) — the single source of truth for well-known
  framework **host** services: `GATEWAY` (9876), `OPENSANDBOX` (8080).
- **`port_manager`** — one registration interface (mirroring the other managers):
  `register(name, port=None, *, preferred=None, kind=...)` records a binding —
  pass an explicit ``port`` for a known bind (Gateway, an env's resolved host
  port), or omit it to allocate one (``preferred`` if free, else OS-assigned).
  `unregister(name)`, `get(name)`, `get_info(name)`, and `list()` round it out.

Every port the framework uses registers here, so the whole system is visible and
de-conflicted in one place. Allocations persist to `output/.runtime/ports.json` (`P.PORTS` in the layout
table), so every process and every run sees the same map.

## What registers, and who owns the value

| Kind | Owner | Examples |
| --- | --- | --- |
| `host` | the framework | `gateway` (9876), `deploy:<site>` (dynamic) |
| `env`  | the environment | `chrome-vnc:novnc`, `playwright:cdp` (the host port the sandbox is reachable on) |

The **value** of an environment's port belongs to that environment (a browser
sandbox knows its own CDP/VNC ports — this module hardcodes no env constants),
but the environment still **registers** its resolved host port here so it shows up
in the one central registry. A new environment does the same: define its ports,
then `register(...)` them.
