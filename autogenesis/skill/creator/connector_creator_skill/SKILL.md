---
name: connector_creator_skill
description: Create new connectors (CONNECTOR.md configs that connect the framework to an MCP server), improve/optimize existing connectors, evaluate connector quality, and — when needed — build a new MCP server to connect to. Use this whenever the task involves adding a connector for an MCP server, writing/editing a CONNECTOR.md, evaluating whether a connector's actions let an agent accomplish tasks, or building an MCP server from scratch (Python FastMCP or Node/TS). MetaAgent uses it to orchestrate the create→evaluate→improve loop across sub-agents.
version: 1.0.0
type: [orchestrator, worker]
license: See LICENSE.txt (server-building guidance adapted from Anthropic mcp-builder)
category: meta
requirements: [cpu]
metadata: {}
---

# Connector Creator

A single skill for the full lifecycle of **connectors** — the framework's bridge to MCP (Model Context Protocol) servers. A connector is a `CONNECTOR.md` that points at an MCP server and declares which of its actions (tools) the framework exposes. This skill covers **creating**, **improving**, and **evaluating** connectors, and — for the case where no server exists yet — **building** an MCP server to connect to (adapted from Anthropic's `mcp-builder`).

Two directions, don't confuse them:
- **A connector CONSUMES an MCP server** — a client-side config (`CONNECTOR.md`: a URL/transport + a list of actions). This is the common case (e.g. connecting to a hosted server like PubMed).
- **An MCP server EXPOSES tools** — server-side code. You only build one when you need to wrap your own API as MCP; then you still write a `CONNECTOR.md` to connect to it.

## How this skill is used — four roles, one body of knowledge

- **MetaAgent (orchestrator role)** — drives the create→evaluate→improve loop, dispatching the sub-agents and running with-connector vs baseline probes. See **Orchestration**.
- **connector_generate_agent** — reads **Creating a connector** (and **Building an MCP server** when the server doesn't exist yet).
- **connector_optimize_agent** — reads **Improving a connector**.
- **connector_evaluate_agent** — reads **Evaluating a connector**.

The three sub-agents are headless: each runs one phase autonomously and returns a result. There is no human-in-the-loop review; the evaluate agent is the automated grader, and the optimize agent iterates on that signal.

## Framework conventions (read once)

- Connectors live in `{extension_root}/connector/{connector_name}/` (generated) or `autogenesis/connector/default/{connector_name}/` (defaults).
- A connector directory:
  ```
  {connector_name}/
  ├── CONNECTOR.md    # REQUIRED — YAML frontmatter (connection + actions) + markdown body (module intro + per-action docs)
  └── references/     # optional — extra docs the agent READs as needed
  ```
- **Naming**: the frontmatter `name` (registry key) follows the `<directory>_connector` convention — directory `pubmed` → `name: pubmed_connector`. Keep it snake_case.
- **Portable stdio connections**: never hard-code machine-specific absolute paths. Use `command: python` and a **relative** script path in `args` (e.g. `server.py`, relative to the connector directory). The connector manager resolves these at load time — `command` → the running interpreter (`sys.executable`), and the relative `*.py` → an absolute path under the connector directory — so the same `CONNECTOR.md` works on any machine/checkout/env. (`streamable_http`/`sse` connectors carry only a `url` and need no paths.)
- **CONNECTOR.md frontmatter** — required: `name`, `description`, `version`, `type`, plus `connection` and `actions`:
  ```yaml
  ---
  name: pubmed_connector
  description: PubMed — search biomedical literature, fetch article metadata and full text.
  version: 1.0.0
  type: worker
  permission_mode: read_only
  connection:
    transport: streamable_http        # or: stdio | sse
    url: https://pubmed.mcp.claude.com/mcp
    # for a local stdio server instead of url:
    # transport: stdio
    # command: python                 # resolved to sys.executable
    # args:
    #   - server.py                    # relative to this connector dir; resolved to an absolute path
  actions:
    - search_articles
    - get_article_metadata
    - get_full_text_article
  ---
  ```
  The **body** below the frontmatter is a short module intro plus a per-action section documenting what each action does and its arguments — this is what an agent reads to call the connector.
- **Registration is automatic via a hook**: after writing/editing the files, include the connector directory path in your `done_tool` reasoning — the registration hook picks it up.

---

## Creating a connector

**Start from the template**: read `references/connector_md_template.md`, copy it to the connector directory, and fill in the connection + actions.

The common case: an MCP server already exists (hosted, or someone gives you a URL/command) and you write a `CONNECTOR.md` for it.

### 1. Identify the server and how to reach it

From the task, determine the connection: `transport` (`streamable_http` / `sse` for a URL endpoint, `stdio` for a local command) and the `url` (or `command` + `args` for stdio).

### 2. Discover the server's actions

Connect to the server and list the tools it exposes — don't guess. Use the bundled probe:
```bash
python {skill_dir}/scripts/connections.py <transport> <url-or-command>
```
`scripts/connections.py` is a lightweight MCP client (stdio/sse/streamable_http) that opens a session and lets you enumerate the server's tools and their input schemas. Record the action names and argument schemas — these become the `actions` list and the per-action docs.

### 3. Design the action surface

Follow the MCP tool-design principles in `references/mcp_best_practices.md`:
- Prefer clear, action-oriented names; keep descriptions concise.
- Expose the actions that let an agent accomplish real tasks; you don't have to surface every raw endpoint.
- Note filtering/pagination so agents can keep results focused.

### 4. Write CONNECTOR.md

Fill the frontmatter (`connection` + `actions`) and write the body: a one-paragraph module intro, then a section per action with **what it does**, **when to use it**, and **arguments** (from the discovered schema). Keep the description (frontmatter) both what-it-does and when-to-use, a little pushy so agents reach for it.

Then put the connector directory path in your `done_tool` reasoning so the registration hook installs it.

### If the server doesn't exist yet

If the task requires wrapping an API that has no MCP server, first **Build an MCP server** (next section), host/run it, then come back and write the `CONNECTOR.md` pointing at it.

---

## Building an MCP server

*(Adapted from Anthropic's mcp-builder. Only needed when no server exists to connect to.)*

Creating a high-quality MCP server is a four-phase process. The quality of a server is measured by how well it lets an agent accomplish real-world tasks.

### Phase 1 — Research & planning
- Understand modern MCP design: balance comprehensive API coverage with focused workflow tools; use clear, prefixed, action-oriented tool names; return concise, filterable results; write actionable error messages. See `references/mcp_best_practices.md`.
- Study the MCP spec (start at `https://modelcontextprotocol.io/sitemap.xml`; fetch pages with a `.md` suffix) and the framework docs for your language.
- Plan the tools before writing code.

### Phase 2 — Implementation
- **Python (FastMCP)**: follow `references/python_mcp_server.md`.
- **Node/TypeScript (MCP SDK)**: follow `references/node_mcp_server.md`.
- Set up the project, core infrastructure, then implement the tools with clear schemas and error handling.

### Phase 3 — Review & test
- Check code quality; build and run the server; connect to it with `scripts/connections.py` and confirm the tools list and behave as intended.

### Phase 4 — Evaluations
- Create ~10 evaluation questions and measure the server (see **Evaluating a connector** and `references/evaluation.md`).

Once the server runs, write a `CONNECTOR.md` for it (see **Creating a connector**).

---

## Evaluating a connector

Goal: measure whether the connector's actions actually let an agent accomplish tasks — empirically, not just by reading the docs.

### Static check (always)

Read the `CONNECTOR.md` and score it: are the required frontmatter fields present (`connection`, `actions`); is each action documented with purpose + arguments; does the description state what-it-does and when-to-use. Use `inspect_connector_tool` to confirm the connector is registered and to get its connection, actions, and directory. Validate structure with:
```bash
python {skill_dir}/scripts/validate_connector.py <connector_dir>
```

### Connection check

Confirm the server is reachable and exposes the declared actions — connect with `scripts/connections.py` and compare the live tool list against the `actions` in the frontmatter. Flag missing or undocumented actions.

### Empirical check (with-connector vs baseline)

The heart of quantitative evaluation is: do the connector's actions help versus not having them? There is no separate eval tool — **MetaAgent runs the comparison by dispatching agents** (see Orchestration). For each realistic test task:
- **with-connector run**: dispatch `general_agent` with the connector available.
- **baseline run**: dispatch `general_agent` without it.

Compare task success. See `references/evaluation.md` for the evaluation methodology (writing good task questions, judging tool use). Produce a scored report: static + connection + empirical, with concrete improvement suggestions.

---

## Improving a connector

Given evaluation results, make the connector better. Edit its `CONNECTOR.md`:
- **Fix action coverage** — add missing actions the agent needed, or drop noisy ones it never uses.
- **Sharpen per-action docs** — clarify arguments and when-to-use so the agent calls them correctly; add examples for tricky ones.
- **Tune the description** for triggering (what-it-does + when-to-use, a little pushy).
- Keep it lean and explain the *why* in docs rather than piling on rigid rules.

Read the transcripts from the test runs, not just the outputs — if the agent misused an action or couldn't find the right one, that points at a doc or coverage fix. Re-register the edited connector by putting its `CONNECTOR.md` path in your `done_tool` reasoning.

---

## Orchestration (for MetaAgent)

You own the create→evaluate→improve loop; you dispatch the sub-agents rather than doing the phases yourself:

1. **Generate** — dispatch `connector_generate_agent` with the intent (server URL/command + what it should expose). It probes the server, writes the `CONNECTOR.md`, and registers it.
2. **Evaluate** — dispatch the with-connector and baseline runs, then `connector_evaluate_agent` to grade:
   - with-connector: a `general_agent` sub-task that has the connector available.
   - baseline: a `general_agent` sub-task without it.
   Then dispatch `connector_evaluate_agent` to grade the connection, coverage, and task success.
3. **Improve** — dispatch `connector_optimize_agent` with the evaluation results. It edits and re-registers.
4. **Repeat** — go back to step 2 until the connector reliably helps.

Keep a plan/todo of the loop so you don't lose track across rounds.

---

## Reference files

- `references/connector_md_template.md` — the CONNECTOR.md skeleton (frontmatter connection/actions + per-action docs).
- `references/mcp_best_practices.md` — MCP tool-design principles (naming, context, errors).
- `references/python_mcp_server.md` / `references/node_mcp_server.md` — how to build an MCP server.
- `references/evaluation.md` — how to write evaluation questions and judge an MCP server/connector.
- `scripts/connections.py` — lightweight MCP client (stdio/sse/streamable_http) to probe a server's tools.
- `scripts/validate_connector.py` — fast structural validation of a CONNECTOR.md.

---

Core loop, one more time: identify the server → discover its actions → write the `CONNECTOR.md` → run an agent with the connector (and a baseline) on realistic tasks → evaluate → improve → repeat until it reliably helps.
