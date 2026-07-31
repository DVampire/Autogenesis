---
name: tool
description: "Defines atomic callable capabilities backed by Python implementations. Tool signatures are introspected into native function-calling schemas and routed through `tool_manager`."
version: 1.0.0
type: module
category: tool
requirements: []
metadata: {}
---
# Tool

Defines atomic callable capabilities backed by Python implementations. Tool signatures are
introspected into native function-calling schemas and routed through `tool_manager`.

| Path | Responsibility |
|---|---|
| `types.py` | Tool and configuration contracts |
| `context.py` | Registration, dynamic loading, versions, and instances |
| `server.py` | Public execution API and canonical schemas |
| `default/` | Built-in framework tools, including inspect tools |
| `other/` | Optional integrations |

Tools should remain small and atomic. Reusable guidance belongs to Skill; multi-step
orchestration belongs to Workflow. The former `tool/workflow/` location has been retired
(its `todo` tool now lives under `default/`); it was never a public Workflow registry, so
define Workflows in the Workflow module rather than here.

`Tool.progress_policy` optionally declares how the Agent runtime treats repeated calls:
`workspace` invalidates evidence when workspace state changes, `external` and `polling`
allow repeated observations, and `always` bypasses the no-progress guard. Unspecified
tools use the guard's conservative name/kind defaults.
