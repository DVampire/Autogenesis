---
name: simplify_skill
description: Review the changed code for reuse, simplification, efficiency, and altitude cleanups, then apply the fixes. Quality only — it does not hunt for correctness bugs; use code_review_skill for that. Use when asked to clean up, simplify, or improve the quality of a diff.
version: 1.0.0
type: worker
license: N/A
category: code-quality
requirements: [cpu]
metadata: {}
---

# Simplify Skill

You are improving the quality of the changed code, not hunting for bugs. Review
it for reuse, simplification, efficiency, and altitude issues, then fix what you
find. Do not look for correctness bugs — that is what the code_review_skill is for.

## How to run (read first)

Tools: `git_tool`/`bash_tool` for the diff, `grep_search_tool` to find existing
helpers, `read_file_tool` to inspect, `edit_file_tool` to apply fixes.

This is a **single-agent procedure**: work through the four cleanup angles below
yourself, one at a time (not by spawning other agents). Then dedup the findings,
apply fixes with `edit_file_tool`, and finish with `done_tool` (`result` = what
was fixed vs skipped).

## Phase 0 — Gather the diff

Run `git diff @{upstream}...HEAD` (or `git diff main...HEAD` / `git diff HEAD~1`
if there's no upstream) to get the unified diff under review. If there are
uncommitted changes, or the range diff is empty, also run `git diff HEAD` and
include the working-tree changes in scope — the review often runs before the
commit. If a PR number, branch name, or file path was passed as an argument,
review that target instead. Treat this diff as the review scope.

## Phase 1 — Review (work each angle as a separate pass)

Go through the four cleanup angles below one at a time, re-reading the diff for
each. For every finding record `file`, `line`, a one-line `summary`, and the
concrete cost (what is duplicated, wasted, or harder to maintain).

### Reuse

Flag new code that re-implements something the codebase already has — Grep
shared/utility modules and files adjacent to the change, and name the existing
helper to call instead.

### Simplification

Flag unnecessary complexity the diff adds: redundant or derivable state,
copy-paste with slight variation, deep nesting, dead code left behind. Name
the simpler form that does the same job.

### Efficiency

Flag wasted work the diff introduces: redundant computation or repeated I/O,
independent operations run sequentially, blocking work added to startup or
hot paths. Also flag long-lived objects built from closures or captured
environments — they keep the entire enclosing scope alive for the object's
lifetime (a memory leak when that scope holds large values); prefer a
class/struct that copies only the fields it needs. Name the cheaper
alternative.

### Altitude

Check that each change is implemented at the right depth, not as a fragile
bandaid. Special cases layered on shared infrastructure are a sign the fix
isn't deep enough — prefer generalizing the underlying mechanism over adding
special cases.

## Phase 2 — Apply the fixes

After all four angles are done, dedup findings that point at the same
line or mechanism, and fix each remaining one directly. Skip any finding whose
fix would change intended behavior, require changes well outside the reviewed
diff, or that you judge to be a false positive — note the skip rather than
arguing with it. Finish with a brief summary of what was fixed and what was
skipped (or confirm the code was already clean).

## Simplification principles (merged from agent-skills code-simplification)

1. **Preserve behavior exactly** — same output/errors/side-effects/ordering for every input; if unsure a change preserves behavior, don't make it.
2. **Follow project conventions** — match neighboring code; consistency over external preference.
3. **Clarity over cleverness** — explicit beats compact when the compact form needs a mental pause (dense ternary chains, chained reduces with inline logic).
4. **Chesterton's Fence** — understand why code exists (check git blame) before removing it.
5. **Watch over-simplification** — don't inline a helper that named a concept, don't merge unrelated logic, don't chase line-count. Fewer lines is not the goal; faster comprehension is.

Scope to what changed; keep refactors separate from feature/bug-fix changes.
