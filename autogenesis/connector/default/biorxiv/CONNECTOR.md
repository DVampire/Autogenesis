---
name: biorxiv_connector
description: bioRxiv & medRxiv preprint servers — search preprints, fetch details, list categories, and check journal publication status.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: streamable_http
  url: https://hcls.mcp.claude.com/biorxiv/mcp
actions:
  - search_preprints
  - get_preprint
  - get_categories
  - search_published_preprints
  - search_by_funder
  - get_content_statistics
  - get_usage_statistics
---

# bioRxiv

An MCP connector for accessing the bioRxiv and medRxiv preprint servers (operated by
Cold Spring Harbor Laboratory). Wraps the official bioRxiv API to provide structured
access to preprint metadata, abstracts, and full-text PDFs. Note: preprints have **not**
undergone peer review.

## Tools

### search_preprints
Find preprints by date range and/or subject category. This is the primary discovery
tool — it does not support keyword, author, or full-text search.

### get_preprint
Get full details (metadata, abstract) for a specific preprint by DOI.

### get_categories
List the available subject categories that can be used to filter searches.

### search_published_preprints
Find preprints that have subsequently been formally published in peer-reviewed journals.

### search_by_funder
Find preprints by funding source (e.g. NIH), for research-funding pattern analysis.

### get_content_statistics
Submission-volume statistics for the preprint corpus.

### get_usage_statistics
Usage statistics (views/downloads) for the preprint servers.

## Typical workflow

1. `get_categories` to identify relevant subject areas.
2. `search_preprints` with a date range + category to find recent activity.
3. `get_preprint` for full details on promising hits.
4. `search_published_preprints` to check whether a preprint was later peer-reviewed.
