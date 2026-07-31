---
name: connector_default
description: "Each sub-directory here defines one **connector** — a wrapper around a single MCP server — via a `CONNECTOR.md` file. Mirrors `autogenesis/skill/default` (where each sub-directory holds a `SKILL.md`): a YAML frontmatter block for metadata + the connection config, followed by a markdown body that documents the module and each of its tools (actions)."
version: 1.0.0
type: collection
category: connector
requirements: []
metadata: {}
---
# Default connectors

Each sub-directory here defines one **connector** — a wrapper around a single MCP
server — via a `CONNECTOR.md` file. Mirrors `autogenesis/skill/default` (where each
sub-directory holds a `SKILL.md`): a YAML frontmatter block for metadata + the
connection config, followed by a markdown body that documents the module and each
of its tools (actions).

`connector_manager.initialize()` scans this directory (and the extension
directory), parses every `CONNECTOR.md`, and loads it. Parsing is offline: it
never opens a network connection, so a bad/unreachable server config will not
break startup. Actions listed under `actions:` in the frontmatter are shown in the
prompt context; call `connector_manager.discover("<name>")` to open a live session
and refresh the real action list.

## CONNECTOR.md format

**Frontmatter (YAML)** — parsed with a full YAML parser, so nested values like
`connection` are supported:

| field            | required | meaning                                                             |
|------------------|----------|---------------------------------------------------------------------|
| `name`           | yes      | Connector name (registry key); convention is `<dir>_connector` (e.g. dir `biomart` → `biomart_connector`). |
| `description`    | yes      | One-line description shown in the prompt context.                   |
| `version`        | no       | Defaults to `1.0.0`.                                                 |
| `type`           | no       | Free-form label (e.g. `worker`); defaults to `worker`.              |
| `permission_mode`| no       | `read_only` / `workspace_write` / `danger_full_access`.             |
| `connection`     | yes      | MCP connection config in `MultiServerMCPClient` format (nested). For stdio, declare it portably — `command: python` and a **relative** `server.py` under `args`; see "Portable paths" below. |
| `actions`        | no       | Statically declared MCP tool names for prompt display.              |
| `action_schemas` | no       | Optional per-action argument schemas.                               |

Any other frontmatter keys are collected into `metadata`.

**Body (markdown)** — module intro + per-tool detailed docs. Stored on
`ConnectorConfig.content` and NOT injected into the prompt context wholesale; the
context only carries name/description/actions plus the `CONNECTOR.md` path, so an
agent can read the full body on demand (progressive disclosure, like `SKILL.md`).

Example — see [`biomart/CONNECTOR.md`](./biomart/CONNECTOR.md):

```markdown
---
name: biomart_connector
description: Ensembl BioMart — genomic annotations, identifier translation, and cross-reference queries.
version: 1.0.0
type: worker
connection:
  transport: stdio
  command: python
  args:
    - server.py
actions:
  - list_marts
  - query
---

# BioMart

Ensembl BioMart — ...

## Tools

### list_marts
Lists all available Biomart marts (databases) from Ensembl.
...
```

## Execution

A connector is self-contained (like a skill) — it is **not** registered into the
tool manager. Call it directly:

```python
await connector_manager(
    name="biomart_connector",
    input={"action": "list_marts", "args": {}},
)
```

## Portable paths (stdio connectors)

Do **not** hard-code machine-specific absolute paths in `connection`. Declare it
relative to the connector and let `connector_manager` resolve it at load time:

```yaml
connection:
  transport: stdio
  command: python          # resolved to sys.executable (the running interpreter)
  args:
    - server.py            # resolved against this connector's own directory
```

`ConnectorContext._resolve_connection` rewrites `command` (any `python`/`python3` or
absolute `.../bin/python`) to `sys.executable`, and any relative `*.py` arg to an
absolute path under the connector directory. So the same `CONNECTOR.md` works on any
machine, checkout location, or Python environment. `streamable_http` (hosted) connectors
carry only a `url` and are left untouched.
