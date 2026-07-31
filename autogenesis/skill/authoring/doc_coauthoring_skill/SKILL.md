---
name: doc_coauthoring_skill
description: "Structured workflow for authoring a substantial written document — proposal, technical spec, decision doc, PRD, RFC, design doc, or similar prose-heavy deliverable. Gather context, draft section by section, then reader-test the draft to catch blind spots before it ships. Use when the deliverable is a structured written document; for data/figure analysis reports use report_design_skill instead."
version: "1.0.0"
type: worker
license: "N/A"
category: writing
requirements: [cpu]
metadata: {}
---
# Doc Co-Authoring Workflow

A discipline for producing a substantial written document (proposal, spec, decision doc, PRD, RFC, design doc) that actually works for its readers — not just a wall of text. Three stages: **gather context → draft section by section → reader-test**. This differs from `report_design_skill` (data/figure reports); here the deliverable is prose-heavy structured writing.

## Tools

- `read_file_tool` — read the task's source material, any template, or existing draft.
- `write_file_tool` — scaffold the document and write full sections.
- `edit_file_tool` — make surgical edits; **never reprint the whole document** for a small change.
- A sub-agent (e.g. `general_agent`) — used in Stage 3 as a fresh "reader" with no prior context (only if your role can dispatch one).

## Stage 1 — Context

Close the gap between what is known and what the document itself conveys. From the task text and any provided files, pin down:

- **Type & audience** — what document is this, and who reads it.
- **Impact** — the single thing a reader should think or do after reading.
- **Template/format** — if one is referenced or provided, read it with `read_file_tool` and follow it.
- **Substance** — the problem, alternatives considered and why they were rejected, constraints/timeline, dependencies, stakeholder concerns.

If a human is in the loop and critical context is missing, ask 5–10 focused clarifying questions. If running autonomously, infer what you can and **state your assumptions explicitly in the draft** rather than stalling.

## Stage 2 — Structure & drafting

1. **Plan sections** for this doc type (decision doc: context / proposal / alternatives / risks / decision; spec: overview / approach / interfaces / testing; etc.). Order by uncertainty: start with the section that has the most unknowns (usually the core proposal or technical approach); leave the summary for last.
2. **Scaffold** — `write_file_tool` a markdown file (e.g. `decision_doc.md`) containing every section header with a placeholder like `[To be written]`.
3. **Fill each section in turn.** For a section: first list the 5–20 candidate points it could cover, keep only the ones that carry weight (drop what the audience already knows, merge duplicates), then draft it and replace the placeholder with `edit_file_tool`.
4. **Refine** with targeted `edit_file_tool` edits as you re-read — never rewrite the whole file for a local change.

## Stage 3 — Reader testing (the key step)

Before declaring the document done, verify it works for someone with **no context**:

1. **Predict reader questions** — 5–10 questions a real first-time reader would bring to this document.
2. **Test with a fresh reader:**
   - *If your role can dispatch a sub-agent:* invoke a fresh `general_agent` given **only** the document content plus the questions (no context from your own run). Ask it to answer each question and to flag anything ambiguous, any unstated assumptions it had to guess at, and any internal contradictions.
   - *Otherwise:* re-read the document adversarially as if seeing it for the first time, answering each question strictly from the text.
3. **Fix blind spots** — wherever the reader got something wrong or flagged a gap, that is a defect in the document, not the reader. Loop back to Stage 2 and fix the offending section.
4. **Repeat** until the reader answers consistently and surfaces no new gaps or ambiguities.

## Quality bar

- Every sentence carries weight — cut generic filler and "slop".
- No redundancy or contradictions across sections.
- After ~3 refinement passes with no substantive change to a section, it's done.
- Use appendices for depth so the main document stays lean.
- Do a final end-to-end read for flow and completeness before finishing.
