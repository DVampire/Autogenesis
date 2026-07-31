---
name: canvas
description: "Visual flow editor. Flow graphs are JSON (the source of truth), run ephemerally on the shared workflow runtime, and are reused via a JSON library under extension/canvas/. Isolated from the agent system's HTML workflows."
version: 1.0.0
type: module
category: orchestration
requirements: []
metadata:
  document_version: 3
---
# Canvas

The canvas is the web UI's **visual flow editor**. A flow is a port/edge graph
stored as **JSON** — the editable source of truth. The canvas owns no executor:
running a flow compiles it to a `WorkflowDefinition` and starts it on the shared
`workflow_runtime` as an **ephemeral** run (nothing is persisted or registered).

It is deliberately **isolated from the agent system's workflows**. Canvas flows
(JSON, full data-flow vocabulary incl. plugins/datasource/process/knowledge) and
agent workflows (`<workflow>` HTML DSL under `extension/workflow/`, authored by
the MetaAgent) are two separate systems with different storage formats. A canvas
flow never becomes an agent workflow and is never callable by an agent.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Flow graph documents (nodes/edges) + palette specs (`NodeSpec`) |
| `catalog.py` | Palette: io + control-flow + live agent/tool/datasource(plugin)/process/knowledge/data/benchmark/workflow entries |
| `compiler.py` | Graph → `WorkflowDefinition` (validated by the real `WorkflowCompiler`) for ephemeral runs; also the bridge that derives control-flow bodies from output edges |
| `server.py` | `canvas_manager`: JSON drafts, the reuse library, ephemeral runs |

## Storage & reuse

- **Session drafts**: JSON under the session's `<project root>/canvas/`.
- **Reuse library**: `export_to_library` saves a flow as JSON under
  `extension/canvas/<name>.json`; `import_from_library` loads it back as a fresh
  draft. The library surfaces as the **`canvas` capability kind** in the
  Capabilities browser (a human-facing library, not agent-callable).
- **Runs**: compile in memory → `workflow_runtime` as `EPHEMERAL`; the canvas
  neither registers workflows nor writes to `extension/workflow/`.

## Boundary with the agent system

The two systems share only the **execution engine** (`WorkflowCompiler` +
`workflow_runtime` + `StepType` grammar) — like two languages compiling to one
VM. They do **not** share identity, storage, authoring, or the reuse registry.
The MetaAgent's orchestration vocabulary stays at the agent/tool/skill layer;
data-flow primitives (plugins/datasource/process/knowledge) are canvas-only.
