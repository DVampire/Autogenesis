---
name: latex-output
description: Use when user requests LaTeX format output or has provided school/journal LaTeX templates
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# LaTeX output

Emit the paper as LaTeX, with support for a university or journal template supplied by the user.

## When to use

1. The user explicitly asks for LaTeX output
2. The user supplied a LaTeX template
3. The target journal or university requires LaTeX

## Template directory

The user can drop template files into `latex-templates/`:

```
latex-templates/
├── README.md              # usage notes
├── template.cls           # template class file
├── template.sty           # template style file
└── main-template.tex      # example main file
```

## Checklist

- [ ] Check `latex-templates/` for a user template
- [ ] Ask the user whether to use it
- [ ] Parse the template structure (sectioning commands, formatting requirements)
- [ ] Create the `.tex` chapter files against the template
- [ ] Create `main.tex`
- [ ] Create `references.bib`
- [ ] Verify that it compiles

## Parsing the template

### Sectioning commands

Common sectioning commands:

```latex
\chapter{...}        % chapter
\section{...}        % section
\subsection{...}     % subsection
\subsubsection{...}  % sub-subsection
```

### Special environments

```latex
\begin{abstract}...\end{abstract}  % abstract
\begin{keywords}...\end{keywords}  % keywords
\begin{figure}...\end{figure}      % figure
\begin{table}...\end{table}        % table
\begin{equation}...\end{equation}  % equation
```

## Output structure

### With a template

```
paper-project/
├── latex-templates/        # original template (leave untouched)
├── chapters/               # chapter content (.tex)
│   ├── 00-abstract.tex
│   ├── 01-introduction.tex
│   ├── 02-literature.tex
│   └── ...
├── figures/                # figure files
├── main.tex                # main file
├── references.bib          # bibliography
└── plan/                   # project plan
```

### main.tex skeleton

```latex
\documentclass{template}  % or the user's template class

% Load the user's template styles
\usepackage{template}

% Basic setup
\title{Paper title}
\author{Author}
\date{\today}

\begin{document}

\maketitle

% Abstract
\input{chapters/00-abstract}

% Table of contents
\tableofcontents

% Body chapters
\input{chapters/01-introduction}
\input{chapters/02-literature}
\input{chapters/03-methods}
\input{chapters/04-results}
\input{chapters/05-discussion}
\input{chapters/06-conclusion}

% Bibliography
\bibliographystyle{gbt7714-numerical}  % or another style
\bibliography{references}

\end{document}
```

## Chapter file format

### Example `.tex` chapter

```latex
% chapters/01-introduction.tex
% Introduction

\chapter{Introduction}

\section{Background}

As [technology] advances, the field of [domain] faces the challenge of [problem].
This paper addresses [problem] and proposes [method].

\section{Objectives and significance}

This study aims to ...

\subsection{Theoretical significance}

...

\subsection{Practical significance}

...

\section{Scope and methods}

The scope of this work covers:

\begin{enumerate}
    \item Part one ...
    \item Part two ...
    \item Part three ...
\end{enumerate}

\section{Structure of the paper}

The paper is organized into X chapters:

Chapter 1 is the introduction, which presents ...
Chapter 2 reviews the literature on ...
...
```

## Bibliography (BibTeX)

### `references.bib` format

```bibtex
@article{author2023title,
    author = {Zhang, San and Li, Si},
    title = {Paper title},
    journal = {Journal name},
    year = {2023},
    volume = {10},
    number = {2},
    pages = {100-110},
}

@book{author2022book,
    author = {Wang, Wu},
    title = {Book title},
    publisher = {Publisher},
    year = {2022},
    address = {Place of publication},
}

@inproceedings{author2021conf,
    author = {Zhao, Liu},
    title = {Conference paper title},
    booktitle = {Conference name},
    year = {2021},
    pages = {50-55},
}
```

For Chinese-language entries, keep the original CJK author names and titles in the `.bib` file and compile with XeLaTeX plus a GB/T 7714 bibliography style.

## Adapting to common templates

### Tsinghua University (ThuThesis)

```latex
\documentclass[degree=master]{thuthesis}
```

Special commands:
- `\thusetup{...}` — set thesis metadata
- `\makecover` — generate the cover
- `\frontmatter` — front matter
- `\mainmatter` — main matter
- `\backmatter` — back matter

### University of Chinese Academy of Sciences (ucasthesis)

```latex
\documentclass{ucasthesis}
```

### Journal templates

Journal formats vary; parse whatever template the user provides.

## Compilation

Record the compile commands in `plan/notes.md`:

````markdown
## LaTeX compilation

### Recommended toolchains
- TeXLive (cross-platform)
- MacTeX (macOS)
- MiKTeX (Windows)

### Commands
```bash
xelatex main.tex
bibtex main
xelatex main.tex
xelatex main.tex
```

### One-shot
```bash
latexmk -xelatex main.tex
```
````

## Converting from Markdown

### Markdown to LaTeX

If the user already has Markdown content, convert it:

1. Heading: `# Title` → `\chapter{Title}`
2. Bold: `**text**` → `\textbf{text}`
3. Quote: `> quote` → `\begin{quote}quote\end{quote}`
4. Code: `` `code` `` → `\texttt{code}`
5. List: `- item` → `\begin{itemize}\item item\end{itemize}`

### Watch out for

- LaTeX special characters must be escaped: `# $ % & _ { } ~ ^`
- CJK text requires XeLaTeX
- Use relative paths for figures

## Error handling

### No template found

> "No LaTeX template detected. Choose one:
> 1. Supply the template files (drop them into `latex-templates/`)
> 2. Use the default `article` class
> 3. Use the `ctexart` class (Chinese)
> 4. Stay with Markdown"

### Incomplete template

> "A template was detected, but [filename] is missing.
> Please complete the template, or fall back to the defaults."
