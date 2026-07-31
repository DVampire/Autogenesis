---
name: workflow_default
description: "Each `.html` file is a complete standalone HTML document and an independently versioned, active Workflow definition loaded by `WorkflowManager.initialize()`. It links the shared `visual/css/workflow.css` and `visual/js/workflow.js` preview assets while keeping the executable `<workflow>` element intact. Keep examples generic and parameterized; project-specific or automatically distilled Workflows belong in `extension/workflow/`."
version: 1.0.0
type: collection
category: workflow
requirements: []
metadata:
  workflow_collection_version: 1.0.2
---
# Built-in workflows

Each `.html` file is a complete standalone HTML document and an independently versioned,
active Workflow definition loaded by `WorkflowManager.initialize()`. It links the shared
`visual/css/workflow.css` and `visual/js/workflow.js` preview assets while keeping the
executable `<workflow>` element intact. Keep examples generic and parameterized; project-specific
or automatically distilled Workflows belong in `extension/workflow/`.

Built-ins are frozen (`enable-evolving="false"`). Evolution produces an evolvable
extension Workflow instead of overwriting package resources. Like generated Tool and
Skill instances, it is live immediately and must be evaluated and rolled back if it regresses.

## Files

- `parallel_review.html` — parallel independent review, per-finding verification, and
  final synthesis. Workflow version `1.0.2`, schema version `1.1.0`.

When changing behavior, increment the Workflow's `version`. When using new language
syntax, update `schema-version` and the root Workflow README compatibility section.
