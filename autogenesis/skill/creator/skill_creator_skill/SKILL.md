---
name: skill_creator_skill
description: Create new skills, improve/optimize existing skills, and evaluate skill quality — the full skill lifecycle. Use this whenever the task involves authoring a skill from scratch, editing or improving an existing skill, evaluating/scoring a skill, running test cases to measure whether a skill helps, or tuning a skill's description for better triggering. MetaAgent uses it to orchestrate the create→evaluate→improve loop across sub-agents.
version: 1.0.0
type: [orchestrator, worker]
license: Apache-2.0 (adapted from Anthropic skill-creator, see LICENSE.txt)
category: meta
requirements: [cpu]
metadata: {}
---

# Skill Creator

## Invocation schema

Every new parameterized Skill declares `input_schema` in SKILL.md frontmatter using JSON
Schema expressed as YAML. Skills that take no invocation arguments omit it and receive the
strict empty-object contract. Never use an unbounded permissive schema for a new Skill.

A single skill for the full lifecycle of skills: **creating** new ones, **improving** existing ones, and **evaluating** their quality. Adapted from Anthropic's `skill-creator`; the authoring theory is kept faithfully, while the mechanics are adapted to this framework (agents + MetaAgent orchestration instead of a browser viewer and a human-in-the-loop).

At a high level, the process of building a good skill is a loop:

- Decide what the skill should do and roughly how.
- Write a draft of the skill.
- Run an agent WITH the skill on a few realistic test prompts (and a baseline WITHOUT it).
- Evaluate the results — qualitatively and, where the outputs are objectively checkable, quantitatively.
- Rewrite the skill based on what the evaluation revealed.
- Repeat until it's good, then widen the test set and try again at larger scale.

## How this skill is used — four roles, one body of knowledge

The same knowledge serves four consumers; each reads the slice relevant to its job (its own prompt tells it which):

- **MetaAgent (orchestrator role)** — drives the whole loop. It dispatches the three sub-agents in sequence, runs with-skill vs baseline probes, and decides when the skill is good enough. See **Orchestration** below.
- **skill_generate_agent** — reads **Creating a skill**.
- **skill_optimize_agent** — reads **Improving a skill** (and **Description optimization**).
- **skill_evaluate_agent** — reads **Evaluating a skill**.

The three sub-agents are headless: they run one phase autonomously and return a result. There is no human-in-the-loop review step; the evaluate agent *is* the automated grader, and the optimize agent iterates on that signal.

## Framework conventions (read once)

- Skills live in `{extension_root}/skill/{skill_name}/` (generated skills) or `autogenesis/skill/default/{skill_name}/` (defaults). Use `snake_case` names ending in `_skill`.
- A skill directory:
  ```
  {skill_name}/
  ├── SKILL.md        # REQUIRED — YAML frontmatter + instructions
  ├── scripts/        # optional — Python run via bash_tool (deterministic/repetitive work)
  ├── references/     # optional — docs the agent READs as needed
  ├── resources/      # optional — runtime data files loaded by scripts
  └── examples/       # optional — examples.md; only when scripts/ exists
  ```
- **Registration is automatic via a hook**: after you finish writing/editing the files, include the skill directory path in your `done_tool` reasoning — the registration hook picks it up. Do NOT package a `.skill` file; this framework registers from the directory.
- **Frontmatter** must include `name`, `description`, `version`, and `type`. `type` is one or more labels: `worker` (an SOP for one agent — visible to sub-agents) and/or `orchestrator` (a composition recipe for MetaAgent — how to fan work across sub-agents). Most skills are `worker`.

---

## Creating a skill

### Capture intent

Start by understanding the intent. The task (or conversation history) may already contain the workflow to capture — the tools used, the sequence of steps, the input/output formats. Extract those first. Pin down:

1. What should this skill enable an agent to do?
2. When should it trigger? (what user phrasings/contexts)
3. What's the expected output format?
4. Are there objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps)? Those benefit from test cases. Subjective outputs (writing style, design) usually don't.

### Write the SKILL.md

**Start from the template**: read `references/skill_md_template.md`, copy it, and fill it in.

Fill in these components:

- **name**: the skill identifier (`snake_case`, ends in `_skill`).
- **description**: the primary triggering mechanism — include both **what** the skill does AND the specific **when to use** contexts. All "when to use" info goes here, not in the body. Agents tend to *under*-trigger skills, so make the description a little **pushy**: instead of "How to build a dashboard", write "How to build a dashboard. Use this whenever the user mentions dashboards, data visualization, or wants to display any kind of data, even if they don't explicitly say 'dashboard.'"
- **version**, **type**, **requirements**, **metadata**: per the conventions above.
- **the body** — the actual instructions.

### Skill writing guide

#### Progressive disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) — always in context (~100 words).
2. **SKILL.md body** — in context whenever the skill triggers (<500 lines ideal).
3. **Bundled resources** (scripts/references) — loaded/executed only as needed (unlimited; scripts run without loading into context).

Keep SKILL.md under ~500 lines. If you approach that, add a layer of hierarchy: move detail into `references/` and point to it clearly from SKILL.md ("read `references/x.md` when you need Y"). For large reference files (>300 lines), include a table of contents.

**Domain organization**: when a skill supports multiple variants, organize by variant so the agent reads only the relevant reference:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/{aws,gcp,azure}.md
```

#### Principle of lack of surprise

Skills must not contain malware, exploit code, or anything that could compromise security. A skill's contents should not surprise the user relative to its stated intent. Don't create misleading skills or skills designed to facilitate unauthorized access or data exfiltration.

#### Writing patterns

Prefer the imperative form. Define output formats explicitly:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
```
Include examples where useful:
```markdown
## Commit message format
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

#### Writing style

Explain **why** things matter rather than piling on heavy-handed MUSTs. Today's models have good theory of mind — given the reasoning, they go beyond rote instructions. If you catch yourself writing ALWAYS/NEVER in all caps or rigid structures, that's a yellow flag: reframe and explain the reasoning instead. Write a draft, then reread it with fresh eyes and improve it. Keep it general, not overfit to one example.

### Test cases

After the draft, write 2-3 realistic test prompts — the kind of thing a real user would actually say. Save them to `{skill_dir}/evals/evals.json` (prompts only; assertions come later during evaluation):

```json
{
  "skill_name": "example_skill",
  "evals": [
    {"id": 1, "prompt": "User's task prompt", "expected_output": "Description of expected result", "files": []}
  ]
}
```

See `references/schemas.md` for the full schema (including the `assertions` field added during evaluation). You can quickly sanity-check a draft's structure with:
```bash
python {skill_dir}/scripts/quick_validate.py {path_to_skill_dir}
```

When the files are written and validated, put the skill directory path in your `done_tool` reasoning so the registration hook installs it.

---

## Evaluating a skill

Goal: measure whether the skill actually helps, and how good its outputs are — empirically, not just by reading it.

### Static check (always do this)

Read the SKILL.md and score it on: instruction clarity, completeness, structure/format, and whether the description states both what-it-does and when-to-use. Run `scripts/quick_validate.py` for the structural pass (frontmatter present, required fields, sane layout). Use `inspect_skill_tool` to confirm the skill is registered and to get its directory.

### Empirical check (with-skill vs baseline)

The heart of quantitative evaluation is: does the skill help versus not having it? In this framework there is no `claude -p` subprocess and no browser viewer — **MetaAgent runs the comparison by dispatching agents** (see Orchestration). Concretely, for each test prompt:

- **with-skill run**: dispatch `general_agent` on the prompt with the target skill made available (its `skill_allowlist` pinned to `[target_skill]`).
- **baseline run**: dispatch `general_agent` on the same prompt with `skill_allowlist: []` (no skill).

Organize outputs under `{skill_dir}/evals/iteration-N/eval-<id>/{with_skill,baseline}/`. Then grade.

### Grading

For each test case, evaluate the outputs against the assertions (objectively verifiable checks with descriptive names). Where an assertion is programmatically checkable, write and run a small script rather than eyeballing it — faster, reliable, reusable. Save results to `grading.json` per run (use fields `text`, `passed`, `evidence`). Aggregate into a benchmark:
```bash
python {skill_dir}/scripts/aggregate_benchmark.py {skill_dir}/evals/iteration-N --skill-name {name}
```
This produces pass_rate / time / tokens per configuration (with-skill vs baseline), with the delta — the objective signal for whether the skill helps. See `references/schemas.md` for the exact JSON the aggregator expects.

Produce a scored report: per-dimension scores (static) + the with-skill/baseline benchmark (empirical) + concrete improvement suggestions.

---

## Improving a skill

This is the heart of the loop. Given evaluation results (and any concrete complaints about specific test cases), make the skill better.

### How to think about improvements

1. **Generalize from the signal.** A skill is meant to be used across many prompts, not just the handful you're iterating on. Don't put in fiddly overfit changes or oppressively constrictive MUSTs to patch one example. If some issue is stubborn, try a different framing or metaphor — it's cheap to try and you may land on something much better.
2. **Keep it lean.** Remove things that aren't pulling their weight. Read the *transcripts*, not just the final outputs — if the skill is making the agent waste steps on something unproductive, cut the part causing it and see what happens.
3. **Explain the why.** Try hard to explain the reasoning behind everything you ask the agent to do. Even when the signal is terse, understand what the user actually needs and transmit that understanding into the instructions. All-caps ALWAYS/NEVER and rigid structures are a yellow flag — reframe and explain instead.
4. **Look for repeated work across test cases.** If every test run independently wrote a similar helper script or took the same multi-step approach, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and have the skill use it — saving every future invocation from reinventing the wheel.

Take your time here — thinking time is not the blocker. Draft a revision, reread it fresh, improve.

### The iteration loop

1. Apply the improvements to the skill files.
2. Re-run all test cases into a new `iteration-<N+1>/` directory, including the baseline. (For a *new* skill the baseline is always no-skill; for an *existing* skill, the baseline can be the original version — snapshot it before editing.)
3. Re-grade and re-aggregate; compare against the previous iteration.
4. Repeat until the outputs are good, the benchmark stops improving, or you've stopped making meaningful progress.

When re-registering an edited skill, put the edited SKILL.md path in your `done_tool` reasoning so the hook reloads it.

---

## Description optimization (triggering)

The `description` frontmatter is the primary mechanism that decides whether an agent invokes a skill. After creating or improving a skill, it's worth tuning the description for triggering accuracy.

### How triggering works

Skills appear in an agent's skill_context as name + description; the agent decides whether to consult a skill from that alone. Agents only reach for skills on tasks they can't trivially handle themselves — a simple one-step query may not trigger a skill even with a perfect description, because the agent just does it directly. So test queries must be **substantive** enough that an agent would actually benefit from the skill. Simple queries like "read file X" are poor test cases.

### Measuring triggering (general_agent probe)

We do NOT ship a special trigger tool. Triggering is measured with a `general_agent` probe dispatched by MetaAgent:

- Build a set of ~20 realistic labeled queries — a mix of should-trigger (8-10) and should-not-trigger (8-10). The most valuable negatives are **near-misses**: queries that share keywords with the skill but actually need something else. Don't make negatives obviously irrelevant ("write a fibonacci function" as a negative for a PDF skill tests nothing).
- **Judge mode (default, cheap)**: dispatch a `general_agent` with a task that gives it the target skill's name+description alongside a few distractor skills and the labeled queries, and asks it to decide, per query, which skill it would invoke — then report per-query hits/misses/false-triggers and overall accuracy. This mirrors the real selection decision; use the misses to revise the description and re-run.
- *(Higher-fidelity alternative, optional)*: dispatch `general_agent` on each real query with the skill in its `skill_allowlist` and observe whether it actually invokes the target skill. This measures real triggering but costs a full run per query and needs the invocation read from the run's trace.

Revise the description to fix under-triggering (misses) and over-triggering (false triggers), then re-run until accuracy is good. Show the before/after description and the scores.

---

## Orchestration (for MetaAgent)

You (MetaAgent) own the create→evaluate→improve loop. You don't do the phases yourself; you dispatch the sub-agents and drive the loop:

1. **Generate** — dispatch `skill_generate_agent` with the intent. It writes the draft and registers it.
2. **Evaluate** — dispatch the with-skill and baseline runs, then `skill_evaluate_agent` to grade:
   - with-skill: a `general_agent` sub-task whose `args` include `skill_allowlist: ["<skill>"]`.
   - baseline: a `general_agent` sub-task with `args` `skill_allowlist: []`.
   - Launch the two probes in the same round so they finish together; then dispatch `skill_evaluate_agent` to grade and benchmark.
3. **Improve** — dispatch `skill_optimize_agent` with the evaluation results. It edits and re-registers.
4. **Repeat** — go back to step 2 into a new iteration until the benchmark stops improving or the skill is good.

Setting `skill_allowlist` on a sub-task's `args` is how you pin which skills a sub-agent sees (the framework injects it into the sub-agent's context). This is the mechanism behind both the with-skill/baseline comparison and the triggering probe.

Keep a plan/todo of the loop so you don't lose track across rounds.

---

## Reference files

- `references/skill_md_template.md` — the SKILL.md skeleton (frontmatter + progressive-disclosure-aware structure).
- `references/schemas.md` — JSON structures for evals.json, grading.json, and the benchmark.
- `scripts/quick_validate.py` — fast structural validation of a skill directory (pure Python, run via bash).
- `scripts/aggregate_benchmark.py` — aggregate per-iteration run results into a benchmark (pure Python).
- `scripts/utils.py` — shared helpers (SKILL.md parsing).

---

Core loop, one more time for emphasis:

- Figure out what the skill is about → draft/edit it → run an agent with the skill (and a baseline) on realistic test prompts → evaluate the outputs (qualitatively + quantitatively where checkable) → improve → repeat until it's good.
