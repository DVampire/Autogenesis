# LaTeX template parsing guide

Detailed guidance for parsing a LaTeX template.

## Parsing workflow

```
1. Scan the latex-templates/ directory
2. Identify the template type (university / journal / generic)
3. Parse the template structure
4. Extract sectioning commands and formatting requirements
5. Generate the matching chapter files
```

## Identifying the template type

### University thesis template

Typical signs:
- Contains keywords such as `thesis` or `dissertation`
- Defines commands such as `\degree`, `\school`, `\major`
- Includes special front/back matter: cover, declaration, acknowledgements

### Journal template

Typical signs:
- An abbreviated journal name (e.g. `ieee`, `elsevier`)
- Defines commands such as `\journal`, `\volume`, `\doi`
- Usually has no cover page

### Generic template

Typical signs:
- Built on the `article`, `report`, or `book` class
- Uses `ctex` or `ctexart` for Chinese support

## Parsing the key files

### `.cls` file (document class)

```latex
% identify the document type
\ProvidesClass{mythesis}

% identify sectioning commands
\newcommand{\chapter}...
\newcommand{\section}...

% identify special environments
\newenvironment{abstract}...
\newenvironment{acknowledgement}...
```

### `.sty` file (style package)

```latex
% identify package dependencies
\RequirePackage{...}

% identify custom commands
\newcommand{\keyword}[1]{...}
\newcommand{\email}[1]{...}
```

### `main.tex` (main file)

```latex
% identify the document class
\documentclass{mythesis}

% identify the chapter structure
\chapter{Introduction}
\chapter{Literature review}
...

% identify the bibliography style
\bibliographystyle{gbt7714-numerical}
```

## Common university templates

### Tsinghua University (ThuThesis)

```latex
% document class
\documentclass[degree=master]{thuthesis}

% metadata
\thusetup{
  title = {Thesis title},
  degree-name = {Master},
  department = {Department of Computer Science},
  ...
}

% special commands
\makecover          % generate the cover
\frontmatter        % front matter
\mainmatter         % main matter
\backmatter         % back matter
```

**Generated structure:**
```
chapters/
├── cover.tex            # cover (auto-generated)
├── 00-abstract.tex      # abstract
├── 01-introduction.tex
├── ...
├── acknowledgements.tex # acknowledgements
└── appendix.tex         # appendix
```

### Peking University (PKUThesis)

```latex
\documentclass{pkuthss}

\pkusetup{
  ...
}
```

### Zhejiang University (ZJUThesis)

```latex
\documentclass{zjuthesis}
```

### Chinese Academy of Sciences (ucasthesis)

```latex
\documentclass{ucasthesis}
```

## Journal templates

### IEEE

```latex
\documentclass[conference]{IEEEtran}

% common commands
\IEEEauthorblockN{Author Name}
\IEEEauthorblockA{Affiliation}
```

### Elsevier

```latex
\documentclass[review]{elsarticle}

% common commands
\journal{Journal Name}
\begin{highlights}...\end{highlights}
```

## Sectioning command mapping

| LaTeX command | Level | Generated file |
|---------------|-------|----------------|
| `\chapter{...}` | Chapter | `01-xxx.tex` |
| `\section{...}` | Section | inside the chapter file |
| `\subsection{...}` | Subsection | inside the chapter file |
| `\subsubsection{...}` | Sub-subsection | inside the chapter file |

## Special environments

### Abstract

```latex
% template definition
\begin{abstract}
...
\end{abstract}

% generated file
chapters/00-abstract.tex
```

### Keywords

```latex
% common forms
\begin{keywords}
keyword1; keyword2; keyword3
\end{keywords}

% or
\keywords{keyword1, keyword2, keyword3}
```

Chinese templates typically separate keywords with the full-width semicolon `；`.

### Acknowledgements

```latex
% common forms
\begin{acknowledgement}
...
\end{acknowledgement}

% or
\chapter*{Acknowledgements}
```

## Bibliography handling

### BibTeX

```latex
\bibliographystyle{gbt7714-numerical}  % style
\bibliography{references}               % file name
```

Generate `references.bib`.

### BibLaTeX

```latex
\usepackage[backend=biber,style=gb7714-2015]{biblatex}
\addbibresource{references.bib}
```

## Error handling

### Incomplete template

When key files are missing, ask the user to supply them:
```
The template is missing:
- [ ] class file (.cls)
- [ ] example main file (main.tex)

Please complete the template before continuing.
```

### Encoding problems

Detect the file encoding and recommend UTF-8:
```
The template files are GBK-encoded; converting them to UTF-8 is recommended.
```

### Unsupported template

When a template cannot be parsed:
```
This template has an unusual structure. Options:
1. Write against the template's own example by hand
2. Fall back to the generic article/ctexart class
3. Contact the template author for usage instructions
```
