---
name: workflow_creator_skill
description: Create, optimize, and evaluate reusable Autogenesis HTML Workflows. Use when a repeated successful multi-agent orchestration should be retained, when an evolvable Workflow has recurring orchestration-level defects, or when a live version needs evidence for keep, improve, or rollback decisions.
version: 1.2.0
type: [orchestrator, worker]
license: Apache-2.0
category: meta
requirements: [cpu]
metadata: {}
---

# Workflow Creator

One methodology for the complete Workflow lifecycle. A Workflow is a reusable orchestration
program, not an Agent subtype and not a substitute for a Skill's domain instructions.

## Orchestration

MetaAgent uses this lifecycle:

1. Prefer an existing active Workflow when applicability and contracts match.
2. Generate only after a useful orchestration pattern has repeated successfully, or when the
   user explicitly requests a reusable Workflow.
3. Register generated/optimized HTML as `status="active"`; like Tool and Skill, it is live immediately.
4. Dispatch `workflow_evaluate_agent` on at least three representative cases.
5. Record every outcome through `evolution_tool.record_workflow_evaluation`.
6. Keep a healthy version; otherwise optimize, rollback, or unload it.

Do not evolve from a single transient failure. Fix Agent/Tool/Skill quality at its owning
layer; change Workflow only for topology, routing, conditions, fan-out, verification,
retry, aggregation, budget, or termination defects.

## Creating a Workflow

- Inspect active Workflows first and avoid semantic duplicates.
- Generalize concrete task details into typed `<inputs>`.
- Write one complete HTML document to `extension/workflow/{name}.html`.
- Use a `<workflow>` element with `name`, semantic `version`, `schema-version="1.1.0"`,
  `status="active"`, a precise `description`, and `enable-evolving="true"`.
- Include `<applicability>` tags and prose explaining when to use and when not to use it.
- Use only supported callable nodes: `agent`, `tool`, `skill`, `connector`, `environment`,
  `workflow`. Connector and Environment nodes require an `action`.
- Use only bounded control nodes: `parallel`, `map`, `branch`, `loop`, `verify`, `reduce`,
  `checkpoint`. Every loop requires `max-rounds`; all fan-out needs a concurrency bound.
- Values use restricted `${path}` expressions. Never embed JavaScript, Python, handlers,
  shell commands, or arbitrary templates.
- Declare complex input constraints with sibling `<schema for="name">` Draft 2020-12 JSON
  Schema and keep its `type` consistent with the `<input>` attribute.
- Define explicit `<outputs>` and reference guaranteed top-level step results.
- Set node `timeout` and retry/backoff policy where an external capability can stall.
- Compile the file before completion and include its absolute path in `done_tool.reasoning`.

## Improving a Workflow

1. Call `inspect_workflow` first. Stop if missing or `enable_evolving=false`.
2. Read evaluation evidence and identify a Workflow-owned defect.
3. Make the smallest structural change; preserve public name and input/output compatibility
   unless the task explicitly authorizes a breaking change.
4. Increment the semantic version and keep status `active`.
5. Compile and check boundedness, reachability, capability names, and output references.
6. Include the edited absolute HTML path in `done_tool.reasoning` for registration.

Never tune a Workflow to one benchmark case. Prefer parameterization over copying variants.

## Evaluating a Workflow

Evaluation is read-only:

1. Call `inspect_workflow`; confirm name, version, active status, source, and contract.
2. Check schema safety, bounded termination, path coverage, capability existence, retry and
   verification policy, input/output clarity, and applicability precision.
3. Run a representative case when safe. Compare with the prior active version or manual
   orchestration when available.
4. Score outcome quality from 0.0–1.0 and report success, real run id, case id, elapsed time, token cost,
   and concrete notes.
5. Call `evolution_tool` with `action=record_workflow_evaluation`. Recommend keep,
   optimize, rollback, or unload from concrete evidence.

A version is provisionally healthy after at least 3 evaluations, success rate at least
0.8, and average quality at least 0.7. This summary guides retention; it does not create a
second publication state. Representative coverage and the absence of safety or termination
defects remain mandatory.
