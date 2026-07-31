---
name: pubmed_connector
description: PubMed — search biomedical literature, fetch article metadata and full text, and resolve citations and related articles.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: streamable_http
  url: https://pubmed.mcp.claude.com/mcp
actions:
  - search_articles
  - get_article_metadata
  - get_full_text_article
  - find_related_articles
  - lookup_article_by_citation
  - convert_article_ids
  - get_copyright_status
---

# PubMed

An MCP connector for the NIH/NLM PubMed database of biomedical literature. Search the
corpus, retrieve article metadata and (where available) full text, and resolve
identifiers, citations, and related work.

## Tools

### search_articles
Search PubMed for articles matching a query. Primary discovery tool.

### get_article_metadata
Fetch metadata (title, authors, abstract, journal, dates) for an article by PMID.

### get_full_text_article
Retrieve the full text of an article where an open-access full text is available.

### find_related_articles
Find articles related to a given PMID.

### lookup_article_by_citation
Resolve a free-text or structured citation to a specific article.

### convert_article_ids
Convert between article identifier schemes (PMID, PMCID, DOI).

### get_copyright_status
Check the copyright / open-access status of an article.

## Typical workflow

1. `search_articles` to find candidate papers.
2. `get_article_metadata` for details on promising hits.
3. `get_full_text_article` when open-access full text is needed.
4. `find_related_articles` to broaden the set.
