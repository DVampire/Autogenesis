# Canvas — visual workflow editor

The canvas is a visual editor **over the workflow module**. It does not own an
executor or a second orchestration language: a flow drawn on the canvas is
JSON source that compiles into the same `<workflow>` HTML the hand-written
workflows use (see `autogenesis/workflow/default/parallel_review.html`), and
every run — draft or published — executes on the workflow runtime.

```
canvas UI  ←→  flow JSON (editable source of truth)
                  │  compile (one-way, validated by the real WorkflowCompiler)
                  ▼
          <workflow> HTML (build artifact)
                  │  publish → workflow_manager.register()
                  ▼
     a first-class workflow capability (callable by the MetaAgent)
```

## Where node configuration lives (three layers)

| Configuration | Home |
|---|---|
| Invocation params: `<arg>` values, task templates, retries / timeout / concurrency / max-rounds / test | flow JSON → compiled into step attributes and `<arg>` elements in the HTML |
| Capability configuration: tool init config, an agent's model role, API keys | the registries (`capability.configure`); flows only reference capability *names* |
| Visual state: positions, container slots | flow JSON only — dropped at compile time, never in the HTML |

The HTML stays fully self-contained and executable; the JSON additionally
keeps visual state and may hold incomplete drafts that do not compile yet.

## Flow JSON (document_version 2)

Stored one file per flow under `<home>/canvas/flows/`.

- `nodes[]` — `kind: step | input | output`.
  - step: `step_type` (`tool|agent|skill|workflow|map|branch|loop|reduce|verify|checkpoint`),
    `target` (capability name), `task`, `args{}`, `items`, `attrs{}`
    (`retries`, `timeout`, `concurrency`, `max_rounds`, `condition`,
    `condition_mode`, `item_name`, `min_votes`, …), `parent` + `slot`
    (`body|then|else`) for container nesting, `position`.
  - input: `name`, `input_type`, `required`, `default`, `description` → `<inputs>`.
  - output: `name`, `value` → `<outputs>`.
- `edges[]` — whole-value bindings: `param` is `arg:<name>`, `items`, or
  `value`; the bound slot compiles to `${source}` (or `${inputs.<name>}`).
  Inline `${...}` references typed into task text are part of the text; the UI
  renders them as derived dashed edges.

## Compile rules (`autogenesis/canvas/compiler.py`)

- Top-level and per-container steps are ordered topologically by data
  references (bindings + inline refs), with canvas position as the tiebreaker.
- `map`/`loop` children come from `parent`; `branch` uses `slot: then|else`.
- A slot that is both edge-bound and literal is a compile error.
- The generated document carries `<meta name="generated-by" content="canvas">`
  and a do-not-hand-edit banner, and is validated with `WorkflowCompiler`
  before publish/run — anything the canvas emits is guaranteed to register.

## Publish, drift, versions

`canvas.flow.publish` compiles, writes `<home>/canvas/workflows/<name>.html`,
and registers it (`override=True`). If the registered version matches but the
`program_hash` differs, the patch version bumps automatically (the registry
rejects content changes without a version increment). `canvas_manager`
re-registers all published artifacts at startup. `canvas.flow.get` reports
`drifted: true` when the registered workflow's hash no longer matches the last
publish (e.g. the evolver changed it); publishing again overwrites.
Hand-written workflows are not canvas-editable in v1 (a graph→HTML
decompiler-import is a possible v2).

## Runs

`canvas.flow.run` compiles the posted graph in memory, marks the definition
EPHEMERAL, and calls `workflow_runtime.start()` — drafts run without touching
the registry. The UI polls `canvas.run.status` (a `WorkflowRun` dump) and
colors nodes from `frames[*].step_id/state`; map iterations show as a ×N badge.

## Gateway commands

| method | params | result |
|---|---|---|
| `canvas.catalog` | — | palette: structural steps, io nodes, one entry per tool/agent/workflow |
| `canvas.flow.list` | — | flow summaries (`published`, `version`, …) |
| `canvas.flow.get` | `{flow_id}` | `{flow, status: {workflow_name, registered, drifted}}` |
| `canvas.flow.save` | `{flow}` | draft save (incomplete graphs allowed) |
| `canvas.flow.publish` | `{flow_id}` | compile + register; `{workflow_name, version, artifact}` |
| `canvas.flow.delete` | `{flow_id}` | also unregisters a published workflow |
| `canvas.flow.run` | `{session_id, flow, input?}` | `{run_id}` (ephemeral, via workflow runtime) |
| `canvas.run.status` / `canvas.run.cancel` | `{run_id}` | `WorkflowRun` dump / cancel |

## Deliberate v1 limits

- No LLM direct-call node — workflows orchestrate capabilities, not raw models.
- Editing hand-written workflows in the canvas requires the v2 import.
- Run progress is polled (1 s), not pushed.
