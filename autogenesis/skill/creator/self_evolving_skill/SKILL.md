---
name: self_evolving_skill
description: The global playbook for self-evolution — how MetaAgent improves the system's OWN capabilities (agents, prompts, tools, skills, connectors, environments) while serving a user task. Use whenever a task is blocked or degraded by a missing/weak capability, when a sub-agent repeatedly fails for a fixable reason, or when the user explicitly asks to create/improve/evaluate a capability. Provides the cross-cutting loop (decide → generate/optimize → evaluate → adopt or roll back), the enable_evolving gate rules, and how to drive the per-type creator skills. NOT for the user's own deliverable work.
version: 1.2.0
type: [orchestrator]
license: N/A
category: meta
requirements: [cpu]
metadata: {}
---

# Self-Evolving Skill (global playbook)

This is the **cross-cutting** methodology for evolving the system's own capabilities.
The per-type *creator* skills (`agent_creator_skill`, `tool_creator_skill`,
`skill_creator_skill`, `connector_creator_skill`, `environment_creator_skill`) tell you
**how** to build/optimize/evaluate one entity of that type. This skill tells you **when
to evolve, which loop to run, how the evolvability gate works, and how to decide whether
a change actually helped** — the parts that are the same across all types.

## What "self-evolution" means here (and its honest limits)

- **Two directions, never confuse them.** *User work* (write the app, answer the
  question) is done by `code_agent` / `general_agent` (`category: actor`). *Self-evolution*
  changes the framework's own capabilities and is done by the generate/optimize/evaluate
  agents (`category: generator/optimizer/evaluator`). Evolution serves the task; it is
  never the deliverable unless the user asked for it.
- **Register-is-live, no candidate pool.** When a generated/optimized entity is
  registered, it becomes the active version immediately (visible to the *next* dispatched
  sub-agent, not one already running). There is **no separate "candidate → validate →
  promote" staging** — so you must **evaluate before you rely on a change**, and treat a
  live change as provisional until verified.
- **The decision is yours (prose, not code).** Nothing automatically scores an evaluation
  and promotes/rolls back. YOU read the evaluator's scored report and decide. Own that
  decision explicitly in your reasoning.

## The evolvability gate (`enable_evolving`) — hard-enforced

Every capability carries `enable_evolving`. It is **enforced in code**: an optimizer that
tries to overwrite a frozen entity is **blocked at registration**.

- **Built-in entities (`src/…`) are frozen** (`enable_evolving=False`) — do NOT try to
  optimize them; the write will be refused. If a built-in is inadequate, **generate a new
  entity in `extension/`** instead of editing the built-in.
- **Generated entities are evolvable** (`enable_evolving=True`) — these you can optimize in
  later rounds.
- **Always `inspect_<type>` the target first** to read its `enable_evolving` (and whether it
  is even registered). If it reports frozen, pick the "generate a new one" path, not optimize.

## When to trigger evolution

**The core question every defect forces: fix *this deliverable*, or evolve a *capability*?**
When a verifier (e.g. `browser_agent`, `reviewer_agent`) or a failed sub-task surfaces a
problem, decide with this discriminator:

> *If I re-dispatch the same agent with "fix X", will it plausibly succeed using the
> capabilities it already has?*
> **Yes → `continue`** (redo/fix the work — the default). **No, it structurally lacks the
> means and will fail the same way → `evolve`.**

Evolution targets a **capability** defect, not a one-off weak attempt. Trigger only on a
real, observed signal — one of:

1. **Missing capability** — the task needs an operation NO tool/skill/connector provides,
   and retrying with existing ones cannot work → `generator` (build it in `extension/`).
   *Example: the deliverable needs real product images and there is no image/media search tool.*
2. **Recurring structural failure** — the same agent fails the same way **≥2×** despite
   corrective guidance → the fault is in its prompt/tool, not the attempt → `optimizer`
   (if the target is evolvable) or `generator` (a skill that encodes the fix).
   *Example: a code agent keeps emitting oversized single actions that fail to parse.*
3. **Quality ceiling from a missing method** — output is *systematically* below bar on a
   dimension because the agent has no method/knowledge to do better and per-task
   instruction won't close the gap → `generator` (a skill carrying the methodology).
   *Example: UIs keep coming out generic because no design skill is being consulted.*

**Check the cheap fixes BEFORE evolving** — most "missing capability" is really "not
wired in / not used":
- Is a suitable capability already registered but **not in the roster / allowlist**? Add it,
  don't regenerate a duplicate. (E.g. a web-search or media tool that exists but wasn't loaded.)
- Did the sub-agent **ignore an existing skill** it should have used? Re-dispatch instructing
  it to invoke that skill (e.g. a design skill for UI), rather than building a new one.
- Only `generator` when the capability is genuinely absent.

**Do NOT evolve** on a first-time fixable deliverable defect (→ `continue`), a one-off
transient error (→ retry), when the budget is TIGHT/CRITICAL (→ finish the task), or to
"improve" a frozen built-in (blocked at registration — generate an `extension/` capability).

## The loop (run it as ordered rounds)

All steps are `kind="agent"`. Pick the sub-agent by type + phase (see the per-type creator
skill for the exact agent names, e.g. `tool_generate_agent` / `tool_optimize_agent` /
`tool_evaluate_agent`).

1. **Assess** — `inspect_<type>` the target: registered? `enable_evolving`? source path.
   Decide generate (missing / frozen built-in → new) vs optimize (exists & evolvable).
2. **Change** — dispatch the `generator` (new) or `optimizer` (existing), `target_name` set.
   It authors the files in `extension/` and registers them (new entities come out evolvable).
3. **Evaluate** — dispatch the `evaluator` for that type → a scored, per-dimension report.
4. **Prove it helped (with-vs-baseline)** — for a capability meant to help task execution,
   dispatch the SAME actor agent twice on a representative probe task: once **with** the new
   capability and once **without** it (baseline). You gate what a sub-agent sees by passing
   an allowlist in its task `args`: `{"tool_allowlist": [...]}` / `{"skill_allowlist": [...]}`
   / `{"connector_allowlist": [...]}` — an empty list is the baseline.
5. **Decide (own it)** — from the evaluator score + the with-vs-baseline outcome, and — for a
   substantial change or before finishing the task — an independent `reviewer_agent` pass
   (it verifies hands-on whether the task is done and whether the evolution actually helped,
   returning a `stop` / `continue` / `evolve` verdict):
   - **Helped (evaluation shows a clear improvement)** → keep it (it's already live) and continue the user task using it.
   - **No better / regressed / not evaluated** → you MUST NOT leave it live. Because register-is-live
     means a bad change is already active, **rolling it back is required, not optional**. Use
     `evolution_tool`: `rollback` an optimized entity to its previous version (`list_versions` first
     to see what to restore), or `unload` a brand-new entity that has no prior good version. Then
     either re-dispatch the `optimizer` with the failure evidence, or regenerate. A change that was
     never evaluated counts as unproven — evaluate it or roll it back; never rely on it blind.
6. **Record** — state in your reasoning what you evolved, the score, the decision, and why.

Typical shape: `Round N` generator|optimizer → `Round N+1` evaluator (+ optional baseline
probe in the same round) → `Round N+2` decision (continue user task, or re-optimize).

## Which entity types are evolvable today

`agent`, `prompt` (via agent optimization), `tool`, `skill`, `connector`, `environment` —
each has a creator skill. There is **no** Memory or Evaluation/Verification evolution triad
yet; don't plan rounds that assume one.

## Guardrails

- Never overwrite a frozen (built-in) entity — generate a new one in `extension/` instead.
- Evaluate before trusting a change; a registered change is live but unverified. If it
  regresses, undo it with `evolution_tool` (rollback/unload) rather than leaving it active.
- Keep evolution within the user task's budget; when TIGHT/CRITICAL, stop evolving and
  finish the user task with what works.
- One capability change per optimize step, so the evaluator can attribute the effect.
