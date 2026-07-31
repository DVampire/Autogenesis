# Dynamic HTML workflows

Module version: **1.6.0** · HTML schema: **1.1.0** · Runtime: **1.1.0**

Active workflows are registered capabilities. MetaAgent invokes one directly through its
`workflow__<name>` function. It can call `inspect_workflow` for the complete HTML and
compiled structure; there is no generic search/run/register workflow tool.

A workflow is an executable multi-agent program, not an Agent subtype. Its source is
HTML so agents and people can read, generate, review, diff, and evolve it. The framework
compiles that HTML into constrained internal instructions before `WorkflowRuntime` runs it.
Persisted files require a complete HTML document with DOCTYPE and an `<html>` root.

```html
<workflow name="audit" version="1.0.0" schema-version="1.1.0"
          description="Discover and verify issues" max-agents="100">
  <inputs>
    <input name="paths" type="array" required="true" />
    <schema for="paths">{"type":"array","items":{"type":"string"},"minItems":1}</schema>
  </inputs>
  <flow>
    <map id="findings" items="${inputs.paths}" as="path" concurrency="8">
      <agent id="inspect" name="general_agent" task="Inspect ${path}" />
    </map>
    <verify id="verified" items="${findings}" as="finding"
            agent="general_agent" task="Verify ${finding}" />
    <reduce id="report" items="${verified}" agent="general_agent"
            task="Deduplicate and rank verified findings" />
  </flow>
  <outputs><output name="report" value="${report}" /></outputs>
</workflow>
```

## Language

- `<agent>`, `<tool>`, `<skill>`, `<connector>`, `<environment>`, and `<workflow>` invoke registered capabilities. Connector and Environment nodes require `action`.
- `<parallel>` runs its child steps concurrently.
- `<map items="...">` fans out over a list discovered at runtime.
- `<reduce>` asks one agent to aggregate a runtime list.
- `<branch test="...">` selects `<then>` or `<else>`.
- `<loop max-rounds="...">` repeats bounded child steps and supports `until` plus
  `no-progress-limit`.
- `<verify>` independently checks every item in a runtime list.
- `<checkpoint>` flushes current run state.

Callable nodes support `timeout`, `retries`, `retry-delay`, and `retry-backoff`. Runtime
preflights statically named capabilities before the first side effect and validates Tool,
Skill, Connector, and Environment arguments against each Manager's canonical Schema.

Expressions use a restricted `${path.to.value}` syntax. Workflow HTML cannot contain
scripts and the runtime has no direct filesystem or shell access: side effects remain in
normal capability managers and inherit their permission boundaries.

## Discovery and lifecycle

Built-ins live in `autogenesis/workflow/default/*.html`; project extensions live in
`extension/workflow/*.html`. A newly generated or optimized Workflow is registered active
immediately, matching Tool and Skill. Extension versions are archived, evaluated, and can
be rolled back or unloaded through the normal extension lifecycle.

Runs checkpoint atomically under `output/.runtime/checkpoints/`. Completed agent invocations
are cached by execution key; resume reuses them and restarts incomplete work.

Runtime checkpoints carry `runtime_version="1.1.0"`, an executable program hash, and preserve four levels of state:
the Workflow run, dynamic execution frames, concrete capability invocations, and retry
attempts. `workflow_manager.start()` launches a background run; `get_run()`, `pause()`,
`continue_run()`, and `cancel()` control it. A process restart uses
`workflow_manager.resume(name, checkpoint)`.

Record outcome-level evidence with `WorkflowEvaluation`; successful evidence must reference
a retained terminal run, each run can be recorded once, and health requires three distinct
cases. `evaluation_summary()` reports
current-version health for keep/optimize/rollback decisions. There is no candidate or
promotion state. Every evolved file is archived by ExtensionManager before it becomes the
live version, so regressions can be rolled back.
