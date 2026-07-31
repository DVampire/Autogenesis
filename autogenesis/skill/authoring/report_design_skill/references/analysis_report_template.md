<!--
  Markdown analysis-report template. Copy into the work dir as <name>_report.md and fill in.
  RULE: every figure is embedded with ![caption](file.png) placed under the finding it supports.
  Never replace an embed with a bare filename list. Paths are relative to THIS file.
-->

# <Report title> — <one-line scope>

## Executive summary

- <Headline finding 1, stated as a conclusion.>
- <Headline finding 2.>
- <Headline finding 3.>

## Data & method

- **Source:** <where the data came from / URL>
- **Size:** <N raw rows → M after cleaning; K dropped and why>
- **Computed:** <statistics / transforms / models applied>

## Findings

### <Finding 1: the claim in one sentence>

<Prose: what the data shows and the supporting numbers.>

![<caption describing the figure>](<figure_1.png>)

_<One-line interpretation of the figure above.>_

### <Finding 2: the claim in one sentence>

<Prose + supporting numbers.>

![<caption>](<figure_2.png>)

_<Interpretation.>_

<!-- Repeat one block per finding. If a summary table helps, include it inline: -->

| group | metric_a | metric_b |
|---|---|---|
| <g1> | <v> | <v> |
| <g2> | <v> | <v> |

## Interpretation & caveats

- <What the findings mean in context.>
- <Honest limitations: small n, confounds, artifacts (e.g. Simpson's paradox), etc.>

## Appendix — data & reproduction

- `<raw_dataset.csv>` — raw input data
- `<summary_stats.csv>` — computed statistics
- `<analysis_script.py>` — run `python <analysis_script.py>` to regenerate every figure and this report
