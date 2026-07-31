---
name: genes_ontologies_connector
description: Gene identity and ontologies — MyGene queries, OLS4 ontology terms, GO annotations (QuickGO), UniProt entries, Reactome pathways. Aggregates five public APIs (no auth).
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
  - query_genes
  - list_ontologies
  - search_ontology_terms
  - get_ontology_term
  - get_go_annotations
  - get_uniprot_entries
  - map_reactome_pathways
---

# Genes & Ontologies

A self-contained MCP connector for gene identity and ontologies, aggregating five
**public** APIs (no authentication): **MyGene.info**, **EBI OLS4**, **QuickGO**,
**UniProt**, and **Reactome**.

## Tools

### query_genes
Query genes by symbol/name/id (MyGene.info); returns cross-reference ids
(Entrez, Ensembl, UniProt).
- `query` (str), `species` (str, default "human"), `limit` (int, optional).

### list_ontologies
List ontologies available in EBI OLS (id + title).
- `limit` (int, optional).

### search_ontology_terms
Search ontology terms across OLS, optionally within one ontology.
- `query` (str), `ontology` (str, optional OLS id e.g. "go"), `limit` (int, optional).

### get_ontology_term
Term label, definition, synonyms. Ontology inferred from the OBO id prefix.
- `term_id` (str, e.g. "GO:0006915"), `ontology` (str, optional).

### get_go_annotations
Gene Ontology annotations for a gene/protein (QuickGO).
- `gene` (str, symbol or UniProt accession), `limit` (int, optional).

### get_uniprot_entries
UniProt protein entries by accession or search (human, reviewed).
- `query` (str, e.g. "TP53" or "P04637"), `limit` (int, optional).

### map_reactome_pathways
Reactome pathways a gene/protein participates in.
- `gene` (str, symbol or UniProt accession), `limit` (int, optional).

## Typical workflow

1. `query_genes` to get a gene's identifiers (Entrez/Ensembl/UniProt).
2. `get_uniprot_entries` for the protein; `get_go_annotations` for its GO terms;
   `map_reactome_pathways` for pathway membership.
3. `search_ontology_terms` / `get_ontology_term` to explore any ontology (GO, HP, …);
   `list_ontologies` to discover which are available.

## Notes

- Read-only; hits public MyGene / OLS / QuickGO / UniProt / Reactome endpoints, so
  responses depend on their uptime.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
