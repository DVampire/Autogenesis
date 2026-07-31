# Chapter file templates

Default chapter file layouts for each paper type.

## Chinese thesis (bachelor's / master's / doctoral)

```
chapters/
├── 00-abstract.md        # abstract (Chinese and English)
├── 01-introduction.md    # introduction (background, significance, objectives, scope)
├── 02-literature.md      # literature review
├── 03-methods.md         # methodology
├── 04-results.md         # results and analysis
├── 05-discussion.md      # discussion
├── 06-conclusion.md      # conclusion (summary, contributions, outlook)
└── 07-references.md      # references
```

### What goes in each chapter

| Chapter | Content | Suggested length (master's) |
|---------|---------|------------------------------|
| Abstract | Background, objective, method, results, conclusion | 500–800 characters |
| Introduction | Background, problem, objectives, significance, scope, structure | 3,000–5,000 characters |
| Literature review | State of the field, theoretical foundation, research gap | 5,000–8,000 characters |
| Methodology | Research design, data sources, analytical methods | 3,000–5,000 characters |
| Results | Data presentation, description of results, initial analysis | 5,000–10,000 characters |
| Discussion | Interpretation, comparison with the literature, limitations | 3,000–5,000 characters |
| Conclusion | Main conclusions, contributions, future directions | 1,500–2,500 characters |

## SCI paper (IMRaD)

```
chapters/
├── 00-abstract.md        # Abstract
├── 01-introduction.md    # Introduction
├── 02-methods.md         # Methods / Materials
├── 03-results.md         # Results
├── 04-discussion.md      # Discussion
└── 05-conclusion.md      # Conclusion (some journals fold this into Discussion)
```

### What goes in each section

| Section | Content | Typical length |
|---------|---------|----------------|
| Abstract | Background, objective, methods, results, conclusions | 150–300 words |
| Introduction | Context, gap, purpose | 500–800 words |
| Methods | Study design, data, analysis | 800–1,500 words |
| Results | Findings, tables, figures | 1,000–2,000 words |
| Discussion | Interpretation, comparison, limitations | 1,000–1,500 words |
| Conclusion | Summary, implications | 200–400 words |

## Chinese core journal

```
chapters/
├── 00-abstract.md        # abstract
├── 01-introduction.md    # introduction
├── 02-main-body.md       # body (split as needed)
├── 03-conclusion.md      # conclusion
└── 04-references.md      # references
```

### Splitting the body

Depending on the content, the body can be split into:
- `02a-theoretical-framework.md` (theoretical framework)
- `02b-research-design.md` (research design)
- `02c-analysis.md` (analysis and discussion)

## Conference paper

```
chapters/
├── 00-abstract.md        # Abstract
├── 01-introduction.md    # Introduction
├── 02-related-work.md    # Related Work
├── 03-methodology.md     # Methodology / Approach
├── 04-experiments.md     # Experiments
├── 05-conclusion.md      # Conclusion
└── 06-references.md      # References
```

## Coursework paper / report

```
chapters/
├── 00-abstract.md        # abstract (optional)
├── 01-introduction.md    # introduction
├── 02-main-body.md       # body
├── 03-conclusion.md      # conclusion
└── 04-references.md      # references
```

## File naming conventions

- Use English filenames; CJK characters cause path problems
- Use a two-digit prefix so the files sort correctly
- Separate words with hyphens
- Use `.md` (Markdown) or `.tex` (LaTeX) consistently

## Adjusting the structure

The user may:
1. Add a chapter, e.g. a case study
2. Remove a chapter, e.g. merge discussion into conclusion
3. Reorder chapters as the research requires
4. Rename chapters to fit the content better
5. Split one chapter into several sub-chapters

Record the adjusted structure in `plan/outline.md`.
