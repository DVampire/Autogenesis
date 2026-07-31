# Canvas library (`extension/canvas/`)

Reusable **canvas flows**, stored as JSON (`<name>.json`, a `FlowGraph`).

This is the canvas's human-facing reuse library. The web-UI canvas exports a
flow here (`Export to library`) and imports one back as a fresh draft. The
library surfaces in the Capabilities browser as the **`canvas` capability kind**.

## Isolated from `extension/workflow/`

| | `extension/canvas/` (this) | `extension/workflow/` |
|---|---|---|
| What | Visual canvas flows | Agent-system workflows |
| Format | **JSON** (`FlowGraph`) | **HTML** (`<workflow>` DSL) |
| Author | People, in the canvas | The MetaAgent |
| Vocabulary | Full (incl. plugins/datasource/process/knowledge) | Agent orchestration (agent/tool/skill/connector/control-flow) |
| Agent-callable | No | Yes (`<workflow>`) |
| Evolvable | No (a plain library) | Yes (versioned/evaluated by the extension system) |

The two are deliberately separate: a canvas flow never becomes an agent
workflow, and the MetaAgent never sees the data-flow primitives (plugins,
datasource, …) that canvas flows may contain. They share only the execution
engine (`WorkflowCompiler` + `workflow_runtime`).

Managed by `canvas_manager` (`autogenesis/canvas/server.py`). Files here are
written by the app; edit flows in the canvas, not by hand.
