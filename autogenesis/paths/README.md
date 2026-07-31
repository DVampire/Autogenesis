---
name: paths
description: "Single source of truth for the on-disk layout: one table declaring every path the framework writes, resolved through path_manager. Two roots only — output/ for generated state, extension/ for shared components."
version: 1.0.0
type: module
category: infrastructure
requirements: []
metadata:
  document_version: 1
---
# Paths

Every path the framework writes is declared in one table and resolved through
`path_manager`. Nothing else joins path fragments, so **this module is the disk
contract** — moving a directory is a one-line edit instead of a hunt through the
gateway, the sandbox, the IDE and half a dozen others.

```python
from autogenesis.paths import P, path_manager

path_manager.get(P.SESSION_WORKSPACE, owner="local", session_id=sid)
path_manager.get(P.PORTS)
```

## Two roots, and only two

| Root | Holds | Lifetime |
|---|---|---|
| `output/` | generated, machine- and user-specific state | disposable |
| `extension/` | shared, durable components (skills, tools, workflows, canvas) | versioned with the project |

`writable_roots()` returns exactly these, so the rule is testable rather than a
convention people remember — see `tests/test_paths.py`.

| Variable | Moves |
|---|---|
| `AUTOGENESIS_HOME` | the whole tree — both roots |
| `AUTOGENESIS_EXTENSION_ROOT` | `extension/` alone (a shared component library on another volume) |

Both are resolved here and nowhere else. `extension/` used to have three
answers — `extension_root()` resolved it against `cwd`, skill and connector
joined `"extension/skill"` themselves, and the layout put it under
`AUTOGENESIS_HOME` — so setting that variable relocated generated state and
left every shared component behind. Likewise `project_path()`, which configs use
for `project_root`/`workspace_root`/`log_root`, now resolves through
`project_dir()`: otherwise a config-started run wrote to `./output` while the
gateway wrote to `$AUTOGENESIS_HOME/output`.

There used to be a third location, `./.autogenesis`, holding the port registry,
the sandbox ledger, deploy workspaces and extension staging. The container
created it as **root**, and `scripts/serve-ui.sh`'s chown loop only walks
`output/`, so the host user could neither edit nor delete it. Those all live
under `output/.runtime/` now.

## The tree

```
output/
  .runtime/                     machine-level — belongs to the host, not a user
    ports.json                  port registry
    sandbox_ledger.json         crash-safe container reaping
    deploy/                     deploy workspaces
    checkpoints/<run_id>.json   workflow run checkpoints
    staging/<project_key>/      extension staging
    unbound/                    output produced before anything bound a session
  <owner>/
    state/                      durable, survives every session
      files/  flows/  ide/{extensions,user-data,home}
    sessions/<session_id>/      disposable
      workspace/                the files agent, canvas and IDE all share
      session.json              identity, so the session survives a restart
    runs/<run_id>/              direct (non-gateway) runs
extension/                      shared components
```

## Keys are an enum, not strings

`P` is a `str` Enum, so a typo is a static error with editor completion rather
than a path silently containing a literal `{owner}`. `get()` also validates
placeholders: asking for `SESSION_WORKSPACE` with only `owner` raises
`session_workspace needs ['session_id']` instead of creating a directory called
`{session_id}` that is painful to trace back later.

## One task, one directory — however it was started

A task started from a local config and the same task started from the browser
resolve to the *same* place. Both build their sandbox from `P.SESSION`:

| Entry point | Sandbox root |
|---|---|
| `examples/run_*`, `agent_manager` | `ensure_session_sandbox(ctx)` → `output/<owner>/sessions/<id>` |
| Gateway (`session.create`) | `path_manager.get(P.SESSION, ...)` → `output/<owner>/sessions/<id>` |

This used to diverge: the local path took `config.project_root / <id>` while the
gateway used its own join, so the two produced different trees for identical
work. `ensure_session_sandbox` now defaults to the layout, and passing an
explicit root remains available for callers that deliberately want a separate
tree (the ProgramBench harness) and for tests.

## `tag` is a label, not a directory

Configs used to set `project_root = output/<tag>`, which put `output/meta_agent/`
beside `output/local/` — a config tag and an owner sharing one level, so a user
named `meta_agent` would collide. Nothing ever read `config.tag`; it was only a
local variable used to build that path. Configs now default to
`output/.runtime/unbound`, and `bind_session_roots()` repoints them at the
session sandbox the moment real work starts, so per-run isolation comes from the
session (or `runs/<run_id>`) rather than from the tag.
