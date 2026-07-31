---
name: evidence-driven-writing
description: Use when writing or revising Introduction, Related Work, background, literature synthesis, or any section where references must drive claims
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Evidence-Driven Writing

This skill turns a literature pool into manuscript argument. It is required for Introduction, Related Work, and any background section with citations.

## Hard Gate

Do not write the section until an evidence map and paragraph blueprint exist.

Required artifacts:

- `refs/evidence-map.md` or `plan/evidence-map.md`
- `plan/chapter-blueprints/<section>-blueprint.md`
- `plan/review/evidence-coverage.md`

## Evidence Map

Create one row per usable source:

| Source ID | Citation | Source type | Abstract-level finding | Usable fact | Supported claim | Citation slot | Risk |
|---|---|---|---|---|---|---|---|

Rules:

- Use the user's literature pool first.
- Use only information present in title, abstract, DOI metadata, or user-provided notes unless full text is available.
- One citation must support one concrete claim, not a vague field statement.
- Mark weak or indirect support as `Risk: indirect`.

## Paragraph Blueprint

For each paragraph, define:

```markdown
### Paragraph N
- Role: context / method landscape / limitation / gap / contribution
- Main claim:
- Evidence IDs:
- Contrast or transition:
- Forbidden content:
```

Only after the blueprint is complete may manuscript prose be written.

## Introduction Pattern

A publishable technical Introduction usually follows this chain:

1. Application context and why the problem matters, supported by foundational or survey citations.
2. Existing technical routes, grouped by method family rather than by paper list.
3. Bottleneck cascade: what each route solves and what remains unsolved.
4. Specific research gap that the proposed method can realistically address.
5. Contributions written as prose or a short list only if the target style allows it.

For computer science / engineering SCI drafts, integrate the most relevant related-work synthesis into the Introduction unless the locked outline explicitly requires a standalone Related Work chapter. The section must read as an argument: field pressure, existing routes, unresolved bottleneck, proposed position, and contribution boundary.

Do not end the Introduction with a long mechanical chapter map. One concise manuscript-organization paragraph is enough.

## Related Work Pattern

Organize by theme, not by chronological paper dump:

- Theme opening: define the method family or research stream.
- Evidence synthesis: compare 2-4 sources in the same paragraph.
- Critical boundary: state what the theme does not solve.
- Bridge: explain why the next theme or the proposed method is needed.

## Body Contamination Firewall

User requirements and process notes must not enter manuscript text. Phrases such as "write naturally", "avoid generic wording", "discussion prompt", "fill later", "user should replace", and "this section is a template" belong in plan files, never in chapters.

Compression is not deletion. When shortening, preserve the claim, evidence, method condition, and limitation.

## Anti-Enumeration Gate

Literature-driven sections fail review if they read like a sequence of source notes. Each paragraph must synthesize at least two of the following:

- a problem condition;
- a method family;
- a limitation shared by multiple studies;
- a direct bridge to the proposed method;
- a citation-backed boundary.

If a paragraph can be converted into a table row without losing meaning, it is not yet manuscript prose.

## GPR Sample

For a reusable example of literature-driven argument structure extracted from the user's GPR passage, read `references/gpr-introduction-example.md`. Use it as a pattern, not as content for unrelated papers.
