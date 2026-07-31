---
name: skill
description: "Discovers and executes reusable, filesystem-backed instructions stored as `SKILL.md` plus optional scripts, references, resources, and examples."
version: 1.0.0
type: module
category: skill
requirements: []
metadata: {}
---
# Skill

Discovers and executes reusable, filesystem-backed instructions stored as `SKILL.md` plus
optional scripts, references, resources, and examples.

| File | Responsibility |
|---|---|
| `types.py` | Skill configuration and invocation context |
| `context.py` | Directory discovery, frontmatter parsing, and lifecycle |
| `server.py` | Public execution API and capability schemas |
| category directories | Built-in Skills grouped by purpose |

Skill frontmatter may declare `input_schema`; omitted schemas mean a strict no-argument Skill.
Skills describe reusable problem-solving knowledge, while Workflow persists executable
multi-capability control flow.
