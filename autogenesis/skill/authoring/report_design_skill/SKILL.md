---
name: report_design_skill
description: Produce a polished, self-contained analysis report (markdown or HTML) from findings and generated figures — data/numerical analysis reports, deep-research reports, deep-dive analysis reports, evaluation write-ups. Use whenever the deliverable is a REPORT that presents results together with charts/tables/images. Its core discipline — every figure is EMBEDDED inline (never just listed by filename), each figure sits under the claim it supports, and the finished report is verified to render.
version: 1.0.0
type: worker
license: N/A
category: reporting
requirements: [cpu]
metadata: {}
---

# Report Design Skill

You are producing a **report** — a deliverable someone opens and reads to understand what was found. A report is not a folder of files plus a list of their names; it is a single self-contained document where the prose, the numbers, and the figures tell one story. Use this whenever the task is a numerical/data analysis report, a deep-research report, a deep-dive analysis, or an evaluation write-up, in either markdown or HTML.

## The one rule that is broken most often

**Figures are embedded, never listed.** If your report generated a chart, plot, image, or diagram, it must appear *in the report as a picture*, placed right under the finding it illustrates — not mentioned by filename in a "Generated charts" list. A reader should scroll the report and see the charts; they should never have to go open PNGs by hand.

- Markdown: `![Bill length vs depth by species](scatter_bill_length_vs_depth.png)` — square brackets are required; `!(file.png)` is **wrong** and renders nothing.
- HTML: `<img src="scatter_bill_length_vs_depth.png" alt="...">`, or a `data:` URI when the report must be a single portable file.
- Use paths **relative to the report file** (same directory ⇒ just the filename) so images resolve wherever the report is opened.

If you catch yourself writing a bulleted list of `.png` filenames, stop — that is the failure mode this skill exists to prevent.

### If the report is written by a script

Reports are often emitted by an analysis script (e.g. an f-string in `analyze.py` that writes `report.md`). The rule still holds: **the markdown the script writes must contain the `![]()` embeds**, not a filename list. Concretely:

```python
charts = [
    ("scatter_bill_length_vs_depth.png", "Bill length vs bill depth, colored by species"),
    ("boxplot_body_mass_by_species.png", "Body mass distribution by species"),
]
figures_md = "\n\n".join(
    f"### {caption}\n\n![{caption}]({fname})\n\n_<one-line interpretation of this figure>_"
    for fname, caption in charts
)
report = f"# Analysis Report\n\n{summary}\n\n{stats_table}\n\n## Figures\n\n{figures_md}\n"
```

## Report structure

A good analysis report reads top-to-bottom as a narrative. Default skeleton (drop sections that don't apply):

1. **Title + one-line scope.**
2. **Executive summary** — 3–5 bullets a busy reader can stop at: the headline findings, stated as conclusions, not tasks.
3. **Data / method** — where the data came from, size, how it was cleaned (rows dropped, filters), what was computed. Enough to trust and reproduce.
4. **Findings** — the body. Each finding is a claim in prose, the supporting number/table, and **the figure embedded right there**. One claim → its evidence → its figure, then the next. This interleaving is what makes it a report rather than a stats dump.
5. **Interpretation / caveats** — what it means, and the honest limitations (small n, confounds, artifacts like Simpson's paradox).
6. **Appendix** — data files and how to reproduce (raw dataset, stats CSV, the script). Filenames belong *here*, as provenance — the figures themselves are already embedded above.

Lead with conclusions, support with evidence. Never make the reader assemble the story from raw output.

## Markdown vs HTML

- **Markdown** (`.md`) — the default for analysis/research reports meant to be read in an editor, repo, or previewer. Fast, diff-able, embeds images with `![]()`.
- **HTML** (`.html`) — when the deliverable is a *presented* artifact: a dashboard, a shareable single-file report, something with real visual identity. For HTML, also load **`artifact_design_skill`** for the visual craft (palette, type, layout, self-check) and render it with the `artifact_renderer` environment action. Keep it self-contained: inline CSS/JS and embed each chart as a `data:` URI (or a relative path if the PNGs travel with the file).

Match the format to how the report will actually be consumed; when unsure, markdown is never the wrong answer.

## Report types (quick guide)

- **Data / numerical analysis** — summary statistics, distributions, correlations, group comparisons. Every comparison you assert gets a chart (boxplot / bar / scatter) embedded beside it. Flag statistical artifacts.
- **Deep-research report** — synthesized findings across sources with **inline citations**; embed any figures/tables you produced; a sources/references section at the end. (Pair with `deep_research_skill` for the research itself.)
- **Deep-dive analysis** — a focused investigation of one system/dataset/question: framing, method, layered findings with figures, a clear conclusion.

## Self-check (required)

After writing the report, do not assume it renders — verify:

```bash
python scripts/verify_report.py <path-to-report.md-or-.html>
```

It confirms every generated image in the report's directory is actually **embedded** (not merely named), that each embedded image path resolves to a real non-empty file, and flags the malformed `!(...)` (missing brackets) mistake. Fix whatever it reports — usually by editing the report or the script that emits it — and re-run until it passes. Only then finish.

## References

- `references/analysis_report_template.md` — a markdown analysis-report skeleton with embedded-figure blocks. Copy and fill.
- `references/report_template.html` — a self-contained HTML report skeleton (inline CSS, figure cards). Copy and fill; use with `artifact_design_skill` for polish.
