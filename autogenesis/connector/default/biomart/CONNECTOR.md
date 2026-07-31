---
name: biomart_connector
description: Ensembl BioMart — genomic annotations, identifier translation, and cross-reference queries over the public Ensembl BioMart REST API (no auth).
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
  - list_marts
  - list_datasets
  - list_common_attributes
  - list_all_attributes
  - list_filters
  - get_data
  - get_translation
  - batch_translate
---

# BioMart

A self-contained MCP connector over the **public** Ensembl BioMart REST API
(`martservice`). No authentication and no proprietary endpoints — it wraps
`https://<mirror>.ensembl.org/biomart/martservice`, trying regional mirrors
(useast first) for reliability. Supports genomic annotation lookups, identifier
translation, and cross-reference queries across species.

## Tools

### list_marts
List available marts (databases), e.g. `ENSEMBL_MART_ENSEMBL`. Start here.
- No arguments. Returns `name<TAB>displayName`.

### list_datasets
List datasets in a mart (e.g. `hsapiens_gene_ensembl` for human genes).
- `mart` (str, optional, default `ENSEMBL_MART_ENSEMBL`).

### list_common_attributes
Curated shortlist of the most-used attributes for a gene dataset (gene id, symbol,
Entrez, UniProt, chromosome, coordinates, biotype, description).
- `dataset` (str, optional, default `hsapiens_gene_ensembl`).

### list_all_attributes
Full attribute list for a dataset (can be thousands — filter with `search`).
- `dataset` (str, optional), `search` (str, optional substring).

### list_filters
Filters available to constrain a query on a dataset.
- `dataset` (str, optional), `search` (str, optional substring).

### get_data
Main query: fetch `attributes` from `dataset`, constrained by `filters`. Returns TSV.
- `dataset` (str), `attributes` (list[str]), `filters` (dict, optional; values may be
  comma-separated, e.g. `{"hgnc_symbol": "TP53,BRCA1"}` or `{"chromosome_name": "17"}`).

### get_translation
Translate a single identifier between two attribute types.
- `dataset` (str), `from_attribute` (str), `to_attribute` (str), `value` (str).

### batch_translate
Translate many identifiers at once between two attribute types.
- `dataset` (str), `from_attribute` (str), `to_attribute` (str), `values` (list[str]).

## Typical workflow

1. `list_marts` → `list_datasets` to locate the mart/dataset (e.g. human genes).
2. `list_common_attributes` / `list_all_attributes(search=...)` and `list_filters(search=...)`
   to discover the field and filter names you need.
3. `get_data` for the actual annotation query, or `get_translation` / `batch_translate`
   for ID cross-referencing (e.g. HGNC symbol → Ensembl gene ID / Entrez ID).

## Notes

- Read-only; queries hit public Ensembl mirrors, so responses depend on Ensembl uptime.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
