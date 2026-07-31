---
name: code_review_skill
description: Review the current diff for correctness bugs and reuse/simplification/efficiency cleanups at a chosen effort level (low/medium → fewer, high-confidence findings; high → broader coverage, may include uncertain findings). Use when asked to review a diff, find bugs in a change, or check a branch before merge.
version: 1.0.0
type: worker
license: N/A
category: code-quality
requirements: [cpu]
metadata: {}
---

# Code Review Skill

Review the diff under review for correctness bugs first, plus reuse,
simplification, efficiency, altitude, and conventions cleanups. Pick an effort
level by how much recall vs. precision the task needs.

## How to run (read first)

Tools: `git_tool` / `bash_tool` to get the diff, `read_file_tool` to open
enclosing functions, `grep_search_tool` to find call sites.

This is a **single-agent procedure**: you work through the angles below
yourself, as a structured pass — one angle at a time — not by spawning other
agents. The "angles" are a checklist that keeps recall high; treat each as a
separate read of the diff so one angle's conclusions don't suppress another's.
When you finish, deliver the ranked findings via `done_tool` (`result` = the
findings list).

(If the orchestrator wants to parallelize a large review, that happens at the
task level — it dispatches several workers, each running this skill on its own
slice of the diff. That is the MetaAgent's decision; this skill stays
single-agent and never names or spawns sub-agents.)

## Phase 0 — Gather the diff

Run `git diff @{upstream}...HEAD` (or `git diff main...HEAD` / `git diff HEAD~1`
if there's no upstream) to get the unified diff under review. If there are
uncommitted changes, or the range diff is empty, also run `git diff HEAD` and
include the working-tree changes in scope — the review often runs before the
commit. If a PR number, branch name, or file path was passed as an argument,
review that target instead. Treat this diff as the review scope.

---

## Effort levels

| Level | Fan-out | Verify | Cap |
|---|---|---|---|
| **low** | 1 diff pass, no subagents | none | ≤4 findings |
| **medium** (default) | 3 correctness + 5 cleanup angles × 6 candidates | 1-vote | ≤8 |
| **high** | 3 correctness + 5 cleanup angles × 6, recall-biased | 1-vote | ≤10 |
| **xhigh / max** | 5 correctness + 5 cleanup angles × 8 + sweep | 1-vote | ≤15 |

`low` is precision (only what's visible in the hunk). `medium` is precision
(every finding actionable). `high`/`xhigh`/`max` are **recall** — catching a
real bug matters more than avoiding false positives; err on the side of
surfacing.

---

## Low effort — single pass, no subagents

### Turn 1 — read
One tool call: read the unified diff. Skip test/fixture hunks (`test/`, `spec/`,
`__tests__/`, `*_test.*`, `*.test.*`, `fixtures/`, `testdata/`). No subagents,
no full-file reads.

### Turn 2 — findings
Flag runtime-correctness bugs visible from the hunk alone: inverted/wrong
condition, off-by-one, null/undefined deref where adjacent lines show the value
can be absent, removed guard, falsy-zero check, missing `await`, wrong-variable
copy-paste, error swallowed in a catch that should propagate. Also flag — still
from the hunk alone — new code that duplicates an existing helper visible in the
diff context, and dead code the diff leaves behind.

Do **not** flag style, naming, perf, missing tests, or anything outside the
hunk. Output at most **4 findings**, most-severe first, one line each:
`path/to/file.ext:123 — what's wrong and the concrete failure`. If nothing
qualifies, output exactly `(none)`.

---

## Medium / high / xhigh — multi-angle with verification

### Phase 1 — Find candidates (work each angle as a separate pass)

Go through the finder angles below one at a time (8 angles at medium/high, 10 at
xhigh/max), each surfacing up to 6 (medium/high) or 8 (xhigh/max) candidates with
`file`, `line`, a one-line `summary`, and a concrete `failure_scenario`. Do NOT
let one angle's conclusions suppress another's — re-read the diff fresh for each
angle; if two angles flag the same line for different reasons, record both.

**Correctness angles:**

- **Angle A — line-by-line diff scan.** Read every hunk line by line, then Read
  the enclosing function for each hunk — bugs in unchanged lines of a touched
  function are in scope. For every line ask: what input, state, timing, or
  platform makes this line wrong? Look for inverted/wrong conditions, off-by-one,
  null/undefined deref, missing `await`, falsy-zero checks, wrong-variable
  copy-paste, error swallowed in catch, unescaped regex metachars.
- **Angle B — removed-behavior auditor.** For every line the diff DELETES or
  replaces, name the invariant or behavior it enforced, then search the new code
  for where that invariant is re-established. If you can't find it, that's a
  candidate: a removed guard, a dropped error path, a narrowed validation, a
  deleted test covering a real case.
- **Angle C — cross-file tracer.** For each function the diff changes, find its
  callers (Grep for the symbol) and check whether the change breaks any call
  site: a new precondition, a changed return shape, a new exception, a
  timing/ordering dependency. Also check callees.
- **Angle D — language-pitfall specialist.** Scan for the classic pitfalls of the
  diff's language/framework — JS falsy-zero, `==` coercion, closure-captured loop
  var; Python mutable default args, late-binding closures; Go nil-map write,
  range-var capture; SQL injection; timezone/DST drift; float equality.
- **Angle E — wrapper/proxy correctness** *(xhigh/max).* When the change adds or
  modifies a type that wraps another (cache, proxy, decorator, adapter): check
  that every method routes to the wrapped instance and not back through a
  registry/session/global, and that the wrapper forwards all methods callers use.

**Cleanup angles** (these hunt for quality, not bugs):

- **Reuse** — flag new code that re-implements something the codebase already
  has; Grep shared/utility modules and name the existing helper to call instead.
- **Simplification** — flag unnecessary complexity: redundant or derivable state,
  copy-paste with slight variation, deep nesting, dead code left behind.
- **Efficiency** — flag wasted work: redundant computation or repeated I/O,
  independent ops run sequentially, blocking work on startup/hot paths, closures
  that keep large scopes alive.
- **Altitude** — check each change is at the right depth, not a fragile bandaid.
  Prefer generalizing the underlying mechanism over layering special cases.
- **Conventions (CLAUDE.md)** — find the CLAUDE.md files governing the changed
  code (user-level, repo-root, and any in an ancestor directory of a changed
  file). Only flag a violation when you can quote the exact rule and the exact
  line that breaks it. Name the CLAUDE.md path and quote the rule.

Cleanup, altitude, and conventions candidates use the same `file`/`line`/
`summary` shape; in `failure_scenario`, state the concrete cost (what is
duplicated, wasted, harder to maintain, or which rule is broken) instead of a
crash. **Correctness bugs always outrank cleanup/altitude/conventions findings
when the output cap forces a cut.**

### Phase 2 — Verify (1-vote, 3-state)

Dedup candidates that point at the same line/mechanism, keeping the one with the
most concrete failure scenario. Then re-examine each remaining candidate
adversarially yourself — read the diff and the relevant file(s) and assign
exactly one of:

- **CONFIRMED** — can name the inputs/state that trigger it and the wrong output
  or crash. Quote the line.
- **PLAUSIBLE** — mechanism is real, trigger is uncertain (timing, env, config).
  State what would confirm it.
- **REFUTED** — factually wrong (code doesn't say that) or guarded elsewhere.
  Quote the line that proves it.

Keep **CONFIRMED and PLAUSIBLE**; drop REFUTED.

At medium effort, be precision-biased. At high/xhigh/max it is **recall mode** —
a single non-REFUTED vote carries the finding; do NOT drop on uncertainty:

> **PLAUSIBLE by default** — do not refute a candidate for being "speculative"
> when the state is realistic: concurrency races, nil/undefined on a
> rare-but-reachable path, falsy-zero treated as missing, off-by-one on a
> boundary the code doesn't exclude, retry storms, regex/allowlist that lost an
> anchor. **REFUTED** only when constructible from the code: factually wrong
> (quote the line); provably impossible (type/constant/invariant); already
> handled in this diff (cite the guard); or pure style with no observable effect.

### Phase 3 — Sweep for gaps *(xhigh/max only)*

Run one more finder as a fresh reviewer who has the verified list. Re-read the
diff and enclosing functions looking ONLY for defects not already listed (don't
re-derive anything there). Focus on what the first pass misses: moved/extracted
code that dropped a guard or anchor; second-tier footguns (dataclass default
evaluated once, `hash()` non-determinism, lock-scope shrink, predicate methods
with side effects); setup/teardown asymmetry in tests; config defaults flipped.
Surface up to 8 additional candidates; if nothing new, return empty — don't pad.

## Output

Return findings as a JSON array of at most N objects (N = the effort cap):

```json
[
  {
    "file": "path/to/file.ext",
    "line": 123,
    "summary": "one-sentence statement of the bug",
    "failure_scenario": "concrete inputs/state → wrong output/crash"
  }
]
```

Ranked most-severe first. If more than N survive, keep the N most severe. If
nothing survives verification, return `[]`.

## Review axes & structural remedies (merged from agent-skills code-review-and-quality)

Beyond correctness bugs, weigh every change on five axes: **correctness, readability/simplicity, architecture, security, performance**. Label findings by severity — **Critical** (blocks merge), required (no prefix), **Nit**/**Optional** (author may ignore) — and lead with the highest-leverage issue, not a pile of nits.

Structural smells and the remedy (propose the move, not just the problem):
- Chain of conditionals on the same shape → typed model or explicit dispatcher.
- A new conditional bolted onto an unrelated flow → push it into its own helper/state/policy.
- A "refactor" that relocates complexity without reducing the concepts a reader must hold → prefer the version where whole branches/modes disappear; prefer deleting an abstraction over polishing it.
- Feature-specific logic in a shared module → move it to the owning package; reuse the canonical helper instead of a near-duplicate.
- A change that grows an already-large file (~1000+ lines) → decompose first, then add.

Detailed checks: `references/security-checklist.md`, `references/performance-checklist.md`.
