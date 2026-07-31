---
# name follows the `<directory>_connector` convention (dir `example` -> `example_connector`)
name: my_connector
description: One line — what this MCP server provides and when to use it (this is how an agent decides to reach for it).
version: 1.0.0
type: worker
permission_mode: read_only
connection:
  # transport is one of: streamable_http | sse | stdio
  transport: streamable_http
  # for streamable_http / sse: a URL endpoint
  url: https://example.mcp.host/mcp
  # for a LOCAL stdio server instead of url, use command + args. Keep it portable:
  # command: python           # resolved to sys.executable (the running interpreter)
  # args:
  #   - server.py             # RELATIVE to this connector dir; resolved to an absolute path at load time
  # (do NOT hard-code machine-specific absolute paths)
actions:
  - search_items
  - get_item
---

<!--
TEMPLATE — CONNECTOR.md for an MCP-server connector. Copy to
`extension/connector/{name}/CONNECTOR.md`, fill the frontmatter (connection + the
`actions` you discovered by probing the server with scripts/connections.py), and
document each action below. The body is what an agent reads to call the connector.
List only the actions you actually expose in `actions:` above.
-->

# My Connector

One paragraph: what this server is, what data/capability it exposes, and the kinds
of tasks it helps with.

## Actions

### search_items
What it does and when to use it. **Arguments**: `query` (str, required), `limit`
(int, optional, default 10). Returns a list of matching items.

### get_item
Fetch full details for one item. **Arguments**: `id` (str, required). Use after
`search_items` to expand a promising result.
