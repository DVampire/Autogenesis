---
name: literature-review
description: Use when writing literature review sections - guides searching, organizing, and synthesizing academic sources
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
allowed-tools: Read, Write, Edit, Bash, WebSearch, WebFetch
metadata: {}
---

# Literature review

Searching, organizing, and synthesizing academic sources.

<EXTREMELY-IMPORTANT>
## Core principle: never fabricate a reference

This is the most important rule and it is absolute:

1. **English sources**: reachable by web search, but their existence must be verified
2. **Chinese sources**: tell the user explicitly to search CNKI; the AI supplies the search strategy
3. **Every citation must be traceable and verifiable**
4. **When reference details are uncertain, omit them rather than invent them**
</EXTREMELY-IMPORTANT>

<MCP-INTEGRATION>
## Literature tooling

This skill ships several literature-processing scripts.

### 1. Literature search (`scholar_search.py`)

**Location**: `scripts/scholar_search.py`

**Databases**: PubMed, CrossRef, Semantic Scholar, arXiv

**Output formats**:
- `json` — JSON (default)
- `bibtex` — BibTeX, usable directly in LaTeX
- `ris` — RIS, for EndNote/Zotero
- `apa` — APA citation format
- `mla` — MLA citation format
- `chicago` — Chicago citation format
- `vancouver` — Vancouver citation format

### Usage

```bash
# Basic search
python scripts/scholar_search.py "deep learning transformer"

# Specific databases
python scripts/scholar_search.py "neural network" --sources pubmed,crossref

# Year filter (it is currently 2026; prefer a recent range)
python scripts/scholar_search.py "machine learning" --year 2023-2026

# BibTeX output (for LaTeX papers)
python scripts/scholar_search.py "landslide detection" --format bibtex -o refs.bib

# APA citation output
python scripts/scholar_search.py "attention mechanism" --format apa --limit 5

# JSON output (for programmatic use)
python scripts/scholar_search.py "quantum computing" --format json -o results.json
```

### Output examples

**BibTeX** (for LaTeX):
```bibtex
@article{xu2024,
  title = {CAS Landslide Dataset: A Large-Scale and Multisensor Dataset},
  author = {Yulin Xu and Chaojun Ouyang and Qingsong Xu},
  journal = {Scientific Data},
  year = {2024},
  doi = {10.1038/s41597-023-02847-z},
}
```

**APA** (for in-text citation):
```
Yulin Xu and Chaojun Ouyang (2024). CAS Landslide Dataset...
```

### Database characteristics

| Database | Rate limit | Abstracts | Citation counts | Fields |
|----------|-----------|-----------|-----------------|--------|
| CrossRef | High | Partial | Yes | All |
| PubMed | Medium | Extra request needed | No | Biomedicine |
| Semantic Scholar | Low* | Yes | Yes | All |
| arXiv | Low | Yes | No | CS / physics / math |

\* Configure an API key for Semantic Scholar to raise the limit.
</MCP-INTEGRATION>

## Checklist

- [ ] Confirm the review topic and scope
- [ ] Generate search keywords (English and Chinese)
- [ ] English sources: run the search and organize the results
- [ ] Chinese sources: supply the search strategy and wait for the user
- [ ] Organize the sources by theme
- [ ] Build the evidence-claim map
- [ ] Assign a citation slot to every source
- [ ] Draft the review
- [ ] Verify that every citation is real
- [ ] Update `plan/progress.md`

## 0. The hard gate between literature and body text

Retrieval is not the deliverable. Before writing the Introduction, Related Work, or a state-of-the-field section, convert the sources into an evidence-claim map:

```markdown
| Source ID | Citation | Abstract-level finding | Usable fact | Supported claim | Citation slot | Risk |
|---|---|---|---|---|---|---|
```

Requirements:

1. `Supported claim` must be a sentence that can go into the body, not "this source is relevant".
2. `Citation slot` must name the paragraph role, e.g. "Introduction-P2, lineage of methods" or "RelatedWork-P3, limitations of FL-IDS".
3. Every core claim needs at least one strong supporting source; a key research gap needs two or more sources together.
4. Only information from the title, abstract, DOI metadata, user-supplied excerpts, or full text you actually read may be used.

Without an evidence-claim map, do not claim the literature review is finished.

## 1. Searching

### 1.0 Script-based search (preferred)

**Use `scripts/scholar_search.py` to search several databases in parallel.**

#### Basic usage

```bash
# Search every database, output JSON
python scripts/scholar_search.py "your query" --format json -o results.json

# Specific databases and year range
python scripts/scholar_search.py "deep learning" --sources crossref,semanticscholar --year 2023-2026

# PubMed only (biomedicine)
python scripts/scholar_search.py "hippocampus memory" --sources pubmed --limit 20
```

#### BibTeX output (for LaTeX papers)

```bash
# Write BibTeX to a file
python scripts/scholar_search.py "landslide detection" --format bibtex -o refs.bib

# Print to the console
python scripts/scholar_search.py "transformer attention" --format bibtex --limit 5
```

**Example BibTeX output:**
```bibtex
@article{xu2024,
  title = {CAS Landslide Dataset: A Large-Scale and Multisensor Dataset},
  author = {Yulin Xu and Chaojun Ouyang and Qingsong Xu},
  journal = {Scientific Data},
  year = {2024},
  doi = {10.1038/s41597-023-02847-z},
  url = {https://doi.org/10.1038/s41597-023-02847-z}
}
```

#### Text citation formats

```bash
# APA
python scripts/scholar_search.py "neural network" --format apa --limit 3

# MLA
python scripts/scholar_search.py "machine learning" --format mla --limit 3

# Chicago
python scripts/scholar_search.py "attention mechanism" --format chicago --limit 3
```

**Example APA output:**
```
Yulin Xu and Chaojun Ouyang (2024). CAS Landslide Dataset: A Large-Scale
and Multisensor Dataset for Deep Learning-Based Landslide Detection.
Scientific Data. 10.1038/s41597-023-02847-z
```

#### Search strategy

1. **Start broad**: use CrossRef (fast, high recall, has citation counts)
2. **Narrow**: add a year-range filter
3. **By field**:
   - Biomedicine → PubMed
   - CS / physics / math → arXiv
   - Want AI-recommended related work → Semantic Scholar

#### Example JSON output

```json
[
  {
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer", "..."],
    "year": 2017,
    "journal": "Advances in neural information processing systems",
    "doi": "10.48550/arXiv.1706.03762",
    "citations": 100000,
    "url": "https://doi.org/10.48550/arXiv.1706.03762",
    "_source": "crossref"
  }
]
```

### 1.1 WebSearch (fallback)

**Use WebSearch when the script is unavailable.**

**Databases:**

| Database | Strength | Fields |
|----------|----------|--------|
| Google Scholar | Broadest coverage | All |
| PubMed | Authoritative in biomedicine | Medicine, biology |
| IEEE Xplore | Engineering and technology | CS, electronics |
| arXiv | Preprints | Physics, math, CS |
| Semantic Scholar | AI-augmented search | All |

**Strategy:**

1. Fix the core English keywords
2. Use boolean operators: AND, OR, NOT
3. Use quotes for exact phrases: "deep learning"
4. Constrain the time range: prefer the last 5 years
5. Sort by citation count to find high-impact work

### 1.2 Searching Chinese sources

<HARD-GATE>
The AI cannot search Chinese academic databases directly; the user has to help.
</HARD-GATE>

**Recommended databases:**
- **CNKI (知网)**: the most comprehensive Chinese academic database
- **Wanfang (万方)**: strong on theses and dissertations
- **VIP (维普)**: journal articles
- **Baidu Scholar (百度学术)**: general search

**What the AI provides:**

1. Generated search keywords
2. Search strategy suggestions
3. Organization and analysis once the user supplies the abstracts

## 2. Organizing the sources

### 2.1 Recording a source

Record this for every source:

```markdown
## Source 1
- **Title**:
- **Authors**:
- **Year**:
- **Journal / conference**:
- **DOI / link**:
- **Core position**:
- **Method**:
- **Main conclusions**:
- **Relation to this study**:
```

### 2.2 Classification

Organize by theme, not one entry per source:

```
literature/
├── theoretical-foundation/
├── methods-and-techniques/
├── applications/
└── surveys/
```

## 3. Writing the review

### 3.1 Structure

```
1. Introduction
   - Background
   - Purpose and scope of the review

2. State of the field
   2.1 Theme one
   2.2 Theme two
   2.3 Theme three

3. Critical assessment
   - What existing work contributes
   - Where it falls short
   - Where the field is heading

4. The research gap and how this study is positioned
```

### 3.2 Key points

**Synthesize, don't enumerate**
- Weak: "Zhang (2020) studied A. Li (2021) studied B."
- Strong: "On question X, the field has proceeded along three lines: Zhang (2020) approaches it from A …, while Li (2021) focuses on B …"

**Be critical**
- Don't just describe the work; assess its contribution and its limits
- Name the relationships between studies (supporting, complementary, contradictory)

### 3.3 Writing templates

**Introducing a field:**
```
[Field] has become one of the active areas of [discipline] in recent years.
Since [seminal work], it has developed rapidly, with research concentrated
on [direction 1], [direction 2], and [direction 3].
```

**Presenting a representative study:**
```
[Author] ([year]) proposed [method/theory], contributing [main contribution].
The experiments show [main finding]. The method is nonetheless limited by
[limitation].
```

**Identifying the gap:**
```
Although existing work has made substantial progress on [aspect], [specific
problem] remains inadequately addressed. Specifically, [problem 1] has not been
examined in depth, and [problem 2] lacks systematic study.
```

## 4. Citation formats

### Chinese (GB/T 7714-2015)

```
[1] 作者. 文章题目[J]. 期刊名, 年份, 卷(期): 页码.
[2] 作者. 书名[M]. 出版地: 出版社, 年份: 页码.
```

### English (APA 7th)

```
Author, A. A., & Author, B. B. (Year). Title. Journal, Volume(Issue), pages.
```

## 5. Dialogue templates

### Scenario 0: searching with the script (preferred)

**Run the search:**

```bash
python scripts/scholar_search.py "keywords" --sources crossref,semanticscholar --year 2020-2024 --limit 20 --format json
```

**Then report:**

> "I'll use the scholarly search script to find sources.
>
> **Query**: `[keywords]`
> **Sources**: CrossRef, Semantic Scholar
> **Years**: 2020–2024
>
> **Results** (sorted by citation count):
>
> | # | Title | Authors | Year | Journal | Citations | DOI |
> |---|-------|---------|------|---------|-----------|-----|
> | 1 | [...] | [...] | 2023 | [...] | 156 | [DOI] |
> | 2 | [...] | [...] | 2022 | [...] | 89 | [DOI] |
>
> Want me to pull the full details for any of these?"

### Scenario 1: the user needs English sources (WebSearch path)

> "I'll search for relevant English-language sources.
>
> **Keywords**: [generated keywords]
>
> **Results**:
> 1. [title] — [authors] ([year])
>    - Journal: [name]
>    - Core content: [brief description]
>    - DOI: [link]
>
> **Suggestion**: of these, [source X] is closest to your research."

### Scenario 2: the user needs Chinese sources

> "Chinese academic sources have to be searched on CNKI or a similar database on your side. Here's the search strategy.
>
> **Suggested keywords**:
> - Subject terms: [keyword 1], [keyword 2]
> - Combined: [keyword 1] AND [keyword 2]
>
> **Steps**:
> 1. Go to https://www.cnki.net/
> 2. Choose Advanced Search (高级搜索)
> 3. Enter the keywords above
> 4. Filter: core journals / CSSCI, last 5 years
>
> **Paste the abstracts you find back to me** and I'll organize and analyze them."

### Scenario 3: the user supplied abstracts

> "Got them — I'll organize these sources.
>
> **Source table**:
>
> | # | Authors | Year | Core position | Relation to this study |
> |---|---------|------|---------------|------------------------|
> | 1 | [authors] | [year] | [position] | [relation] |
>
> **Suggested organization**:
> These sources can be grouped along the following lines …
>
> Want me to draft the review paragraphs?"

## 6. Citation checking and verification

### 6.1 Verification (mandatory)

**Use the `verification` skill for a strict check:**

| Claim | Verification | Not sufficient |
|-------|--------------|----------------|
| The reference exists | DOI confirmed via the CrossRef API | "It looks right" |
| The citation format is correct | Run the format-check script | Eyeballing it |
| The author details are accurate | Search the original source | "It's probably fine" |

**Verification commands:**
```bash
# Check that a DOI exists
curl -s "https://api.crossref.org/works/10.1000/doi123"

# Regenerate and validate the BibTeX
python scripts/scholar_search.py "your query" --format bibtex --output refs.bib
```

### 6.2 Parsing PDFs

**When the user supplies a PDF, extract its content with `scripts/pdf_parser.py`:**

```bash
# Extract the text
python scripts/pdf_parser.py paper.pdf --output paper_text.txt

# Extract structure and abstract
python scripts/pdf_parser.py paper.pdf --sections --abstract --json paper_info.json

# Summarize
python scripts/pdf_parser.py paper.pdf --summarize
```

**What comes out:**
- Metadata (title, authors, page count)
- Abstract
- IMRaD sections (introduction, methods, results, discussion)
- An automatic summary

### 6.3 Citation checklist

**Mandatory:**
- [ ] Every cited work genuinely exists (verified by DOI)
- [ ] Author, year, and title are accurate
- [ ] Citation formatting is consistent
- [ ] In-text citations correspond one-to-one with the reference list
- [ ] Every citation has surrounding context explaining its relation to this study
