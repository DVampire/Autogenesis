# Autogenesis

A self-evolving multi-agent framework. A **MetaAgent** orchestrates sub-agents to complete user tasks, while optimizer / evaluator / generator agents continuously improve the tool, skill, and agent ecosystem.

> 🌐 中文版请见 [README_zh.md](README_zh.md)

## Installation

```bash
bash scripts/install.sh
```

Creates a conda environment (`agentos`, Python 3.12), installs the package and
its dependencies, installs Node.js, and writes an `.env` template. Re-running is
safe. Add `--extras browser` for browser automation, `--uv` to use uv instead of
conda, or `--help` for all options.

Then put your API keys in `.env` at the project root:

```bash
ANTHROPIC_API_BASE='...'
ANTHROPIC_API_KEY='...'
OPENROUTER_API_BASE='...'
OPENROUTER_API_KEY='...'
```

Keys can instead be managed centrally in **Vault**, which the framework prefers
whenever it is configured and reachable, falling back to `.env` otherwise.

Full details — manual setup, Vault, and optional extras:
**➡️ [scripts/INSTALL.md](scripts/INSTALL.md)**

## Usage

Autogenesis runs the **entire framework inside a container** (this is "Model X"): the
MetaAgent, every sub-agent, and all tool execution (bash / file edits / git / experiment
code). The host only launches it; the repo is bind-mounted in, so source edits are live
and outputs land back on the host under `output/`. Service peers (browser, task images)
are spawned as sibling containers through the mounted Docker socket over the shared host
network.

Build the base image once:

```bash
docker build -f docker/base/Dockerfile -t autogenesis/base:latest .
```

From then on **everything runs the same way** — hand a command to the launcher after `--`:

```bash
scripts/run-in-sandbox.sh -- <command>          # run <command> in the sandbox
scripts/run-in-sandbox.sh --gpus -- <command>   # ...also exposing NVIDIA GPUs
```

The launcher needs a reachable Docker daemon and refuses to fall back to the host; use
`--image IMG` for a different base image. The bare `<command>` also runs directly on the
host (no container) after `conda activate agentos`, handy for quick local development.

The three things you'll run are below.

### 1. Run a task (MetaAgent)

[`examples/run_meta_agent.py`](examples/run_meta_agent.py) boots the MetaAgent with its sub-agents and runs a single task to completion.

```bash
# Default task
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py

# Inline task
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py --task "Write a Python function to reverse a string and add unit tests."

# Task from a document (.html / .md under examples/tasks/)
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py --task-file examples/tasks/qsar_egfr_experiment.html
```

| Flag | Description |
| --- | --- |
| `--task "<text>"` | Inline task string. Takes priority over `--task-file`. |
| `--task-file <path>` | Path to a task document (`.html` / `.md`) under `examples/tasks/`. |
| `--config <path>` | Config file (default: `configs/meta_agent.py`). |
| `--cfg-options key=value ...` | Override any config field, e.g. `--cfg-options model_name=openai/o3`. |

Each run is its own session: artifacts, logs, and task views land under
`output/<owner>/sessions/<session-id>/` (`workspace/` for the agent's files, `log/` for logs and
rendered task views). On completion the log prints the final result and, if produced, the
path to a memory HTML report. Ready-made task documents live in [`examples/tasks/`](examples/tasks/).

### 2. Interactive web UI

[`frontend/`](frontend/) is a React/Vite browser UI that talks to the Python runtime over the versioned Gateway protocol. Under Model X **both the backend Gateway and the frontend dev server run inside the sandbox** — one container, two processes, started together by [`scripts/serve-ui.sh`](scripts/serve-ui.sh):

```bash
scripts/run-in-sandbox.sh -- scripts/serve-ui.sh
```

Then open `http://127.0.0.1:5173` in the host browser (the Vite dev server); it connects
to `ws://127.0.0.1:9876/ws` by default. The sandbox uses `--network host`, so both ports
are reachable from the host with no extra setup. The first launch runs `npm install`
inside the sandbox (deps land in `frontend/node_modules`; later launches skip it).
Override ports with `GATEWAY_PORT` / `UI_PORT`; args after the script pass through to
`autogenesis serve` (e.g. `--token`, `--allow-origin`).

Set `AUTOGENESIS_GATEWAY_TOKEN` before binding the Gateway outside a trusted local
network — it is required for non-loopback hosts, and browser origins can be restricted with
repeated `--allow-origin`. See [`frontend/README.md`](frontend/README.md) for the full guide.

### 3. Run the tests

```bash
scripts/run-in-sandbox.sh -- pytest -q                        # fast suite
scripts/run-in-sandbox.sh -- pytest -q tests/test_gateway.py  # one file
scripts/run-in-sandbox.sh -- pytest -m integration            # needs creds / services / peers
```

Tests live in [`tests/`](tests/). The default run passes `-m 'not integration'` (see
`pyproject.toml`), so it needs no API keys or Docker peers and finishes quickly.
`scripts/install.sh` already runs this suite once as a post-install check.

## Output & project layout

`autogenesis` has one CLI with three modes: a control command (e.g. `autogenesis /registry`), the terminal loop (`autogenesis tui`), or the Gateway (`autogenesis serve ...`).

There are two writable roots, and only two. Every path the framework writes is declared in
one table (`autogenesis/paths`) and resolved through `path_manager`, so the layout below is
the whole disk contract:

```
output/                        generated state — disposable
  .runtime/                    machine-level: port registry, sandbox ledger, deploy, staging
  <owner>/
    state/                     durable across sessions: files, flows, IDE extensions + logins
    sessions/<session-id>/     one task, one directory (workspace/, session.json)
extension/                     shared, durable components — versioned with the project
```

A task started from a config file and the same task started from the browser resolve to the
*same* directory: both build their sandbox from the layout rather than joining paths
themselves. A session stages extension changes under its own output directory and promotes
them into `extension/` explicitly.

`AUTOGENESIS_HOME` moves the whole tree elsewhere (a shared volume, a scratch disk);
`AUTOGENESIS_EXTENSION_ROOT` moves just the shared component library. There is no longer a
third location — the `./.autogenesis/` directory this used to describe was created by the
container as root, outside the chown loop, so the host user could neither edit nor delete
it; its contents live under `output/.runtime/` now.
