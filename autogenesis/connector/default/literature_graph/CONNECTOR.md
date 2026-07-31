---
name: literature_graph_connector
description: Scholarly literature graph — OpenAlex works/citations/references/authors/venues plus arXiv preprint search. Public APIs, no auth.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: stdio
  command: python
  args:
    - server.py
actions:
  - openalex_search_works
  - openalex_get_work
  - openalex_citations
  - openalex_references
  - openalex_search_authors
  - openalex_get_author
  - openalex_venue_info
  - arxiv_search
  - arxiv_get_papers
---

# Literature Graph

A self-contained MCP connector for the scholarly literature graph, over two **public**
APIs (no authentication): **OpenAlex** (`api.openalex.org`) and **arXiv**
(`export.arxiv.org`). Endpoint mappings referenced from open-source OpenAlex/arXiv MCP
servers (e.g. [benedict2310/Scientific-Papers-MCP](https://github.com/benedict2310/Scientific-Papers-MCP)).

## Tools

### OpenAlex
- `openalex_search_works` — search papers by keyword. Args: `query`, `limit`.
- `openalex_get_work` — full metadata + abstract for a work. Args: `work_id` (OpenAlex id or DOI).
- `openalex_citations` — works that cite a work (incoming). Args: `work_id`, `limit`.
- `openalex_references` — works referenced by a work (its bibliography). Args: `work_id`, `limit`.
- `openalex_search_authors` — search authors by name. Args: `query`, `limit`.
- `openalex_get_author` — author profile (works, citations, h-index, topics). Args: `author_id`.
- `openalex_venue_info` — journal/venue info by name or source id. Args: `query`.

### arXiv
- `arxiv_search` — search preprints (supports `au:`/`ti:`/`cat:` prefixes). Args: `query`, `limit`.
- `arxiv_get_papers` — fetch specific papers by arXiv id. Args: `arxiv_ids` (comma-separated), `limit`.

## Typical workflow

1. `openalex_search_works` / `arxiv_search` to find papers on a topic.
2. `openalex_get_work` for metadata + abstract; `openalex_citations` / `openalex_references`
   to walk the citation graph.
3. `openalex_search_authors` → `openalex_get_author` for researcher profiles;
   `openalex_venue_info` for journal metrics.

## Notes

- Read-only; hits public OpenAlex + arXiv APIs (OpenAlex "polite pool" via a mailto UA),
  so responses depend on their uptime.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
