---
name: my_skill
description: What this skill does AND when an agent should use it. Put ALL "when to use" cues here — this line is the primary trigger, so make it specific and a little pushy.
version: 1.0.0
type: worker
requirements: [cpu]
metadata: {}
---

<!--
TEMPLATE — SKILL.md. Copy to `extension/skill/{name}/SKILL.md`, fill the frontmatter
and body. `type` is one (or more) of: `worker` (an SOP for one agent, visible to
sub-agents) / `orchestrator` (a composition recipe for MetaAgent). Add optional
subdirectories only when needed: scripts/ (Python run via bash_tool), references/
(docs the agent reads), resources/ (runtime data), examples/ (examples.md; only if
scripts/ exists). Keep this body under ~500 lines; push detail into references/.
-->

# Skill Title

Brief overview: what this skill achieves and its primary use case. Explain the WHY
so the agent understands intent rather than following brittle rules.

## Instructions

### Step 1: [First action]
Concrete, imperative description of what to do, including any conditions/decisions.

### Step 2: [Second action]
What to do and how to verify it worked.

### Step 3: Verify and report
How to confirm the task is complete, then call `done_tool` with the result.

## Output format
(If the skill produces a structured artifact, show the exact template here.)

```
[Concrete output template]
```

## Examples
(Optional but valuable — show 1-2 realistic input → output pairs.)
