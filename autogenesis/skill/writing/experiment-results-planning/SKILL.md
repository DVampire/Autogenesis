---
name: experiment-results-planning
description: Use when designing experiments, result tables, mock planning data, evaluation protocols, or results sections before real data are final
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Experiment Results Planning

This skill designs the experiment/result layer before final metrics exist. It may generate mock planning data, but never presents mock data as real experimental evidence.

## Hard Gate

Before writing Results or Discussion, create:

- `plan/experiment-protocol.md`
- `plan/review/method-experiment-traceability.md`
- `tables/table-schema.md`
- `figures/data-manifest.md`
- real data files or clearly labeled `mock_*` files

## Experiment Protocol

The protocol must include:

- Dataset and split strategy.
- Baselines and why each is fair.
- Metrics and imbalance handling.
- Main comparison.
- Efficiency evaluation.
- Ablation studies for each claimed module.
- Generalization or robustness checks.
- Explainability evaluation if XAI is a contribution.

Each contribution in Introduction must map to at least one experiment or limitation note.

## Recommended Experiment Gates

Use these gates in `plan/stage-gates.md` for result-heavy papers:

1. Gate D0: Experiment Protocol Locked
   - Required: datasets, split rules, Non-IID construction, seeds, baselines, metrics, hardware/software, log schema.
2. Gate D1: Method-Experiment Traceability
   - Required: `plan/review/method-experiment-traceability.md`.
   - Map each contribution to method modules, experiments, tables/figures, and allowed claims.
3. Gate D2: Table/Figure Data Contract
   - Required: `tables/table-schema.md`, `figures/data-manifest.md`, and data files.
4. Gate D3: Main/Efficiency/Ablation/Generalization/XAI Results
   - Each result family needs raw logs, aggregation rule, table update, figure script, and prose update.
5. Gate D4: Result Chapter Decontamination
   - No planning notes left in the chapter body. For Chinese manuscripts this means no `实验目的` (experiment purpose), `表位` (table slot), `回填模板` (backfill template), or `讨论提示` (discussion prompt) markers.
6. Gate D5: Peer Review Pass
   - Required: `plan/review/<section>-peer-review.md`.

## Method-Experiment Traceability

Create:

```markdown
| Contribution | Method module | Experiment | Table/Figure | Allowed claim | Evidence status |
|---|---|---|---|---|---|
```

Do not let a contribution survive in Introduction if no experiment, limitation note, or future-work boundary supports it.

## Mock Data Boundary

Mock or synthetic values are allowed only for planning figures and table layout.

Rules:

- File names must start with `mock_` or `synthetic_`.
- Every mock table must contain a note: `PLANNING DATA - replace before submission`.
- Manuscript prose using mock values must keep the placeholder `[待真实实验替换]` ("replace with real experiment"), which is the marker the quality gate greps for.
- Do not describe mock values as "results show", "verified", or the Chinese equivalent `实验结果表明`.

## Table Schema

For each table, define:

| Table | Purpose | Rows | Metrics | Data source | Replacement owner |
|---|---|---|---|---|---|

Do not create a table unless it supports a claim in the manuscript.

Recommended table fields include `mean ± std` or confidence intervals when repeated runs are expected. Record aggregation rules in `tables/table-schema.md`.

## Figure Handoff

Data figures must go through `figures-python`:

1. Write or receive CSV/JSON data.
2. Record it in `figures/data-manifest.md`.
3. Generate `figures/<section>/<figure>.py`.
4. Export PNG and SVG.
5. Write a caption that states what the figure measures, not what the author hopes it proves.

Model architecture and flow diagrams use `figures-diagram` prompts instead of synthetic data plotting.

## Results Prose Pattern

For real data:

```text
The method achieves X under condition Y, compared with baseline Z. The improvement is mainly associated with [module], while [failure case] remains visible in [metric].
```

For planning data:

```text
[待真实实验替换] This paragraph will compare Table N after real experiment logs are inserted.
```

Never leave "experiment purpose", "discussion prompt", or "table position" instructions inside final chapter files.
