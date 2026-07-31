---
name: omics_archives_connector
description: Omics data archives — ArrayExpress/BioStudies experiments, GEO series, MGnify metagenomics, PRIDE proteomics, MetaboLights metabolomics. Public EBI/NCBI APIs, no auth.
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
  - arrayexpress_search_experiments
  - arrayexpress_get_experiment
  - arrayexpress_get_experiment_files
  - arrayexpress_get_experiment_samples
  - geo_search_series
  - geo_get_series
  - mgnify_search_studies
  - mgnify_get_studies
  - mgnify_get_study_analyses
  - pride_search_projects
  - pride_get_projects
  - pride_search_project_proteins
  - pride_find_projects_for_protein
  - metabolights_list_studies
  - metabolights_get_studies
  - metabolights_get_study_files
  - metabolights_search_data_files
---

# Omics Archives

A self-contained MCP connector for omics data repositories, over **public** EBI/NCBI
APIs (no authentication): **ArrayExpress/BioStudies**, **GEO**, **MGnify**, **PRIDE**,
and **MetaboLights**. GEO uses NCBI E-utilities (referenced from the open-source
[MCPmed/GEOmcp](https://github.com/MCPmed/GEOmcp)).

## Tools

### ArrayExpress (BioStudies) — functional genomics
- `arrayexpress_search_experiments` — search experiments. Args: `query`, `limit`.
- `arrayexpress_get_experiment` — experiment metadata. Args: `accession`.
- `arrayexpress_get_experiment_files` — data files. Args: `accession`, `limit`.
- `arrayexpress_get_experiment_samples` — sample/SDRF summary. Args: `accession`.

### GEO — expression series
- `geo_search_series` — search GSE series. Args: `query`, `limit`.
- `geo_get_series` — series details. Args: `gse`.

### MGnify — metagenomics
- `mgnify_search_studies` / `mgnify_get_studies` / `mgnify_get_study_analyses`.

### PRIDE — proteomics
- `pride_search_projects` / `pride_get_projects`.
- `pride_find_projects_for_protein` — projects matching a protein (keyword search).
- `pride_search_project_proteins` — pointer to a project's protein data (no public
  per-project protein-list endpoint exists).

### MetaboLights — metabolomics
- `metabolights_list_studies` / `metabolights_get_studies` / `metabolights_get_study_files`
  / `metabolights_search_data_files`.

## Typical workflow

1. Pick a modality: `arrayexpress_search_experiments` / `geo_search_series` (transcriptomics),
   `pride_search_projects` (proteomics), `metabolights_list_studies` (metabolomics),
   `mgnify_search_studies` (metagenomics).
2. Fetch details (`*_get_*`) and files/analyses/samples for the chosen study.

## Notes

- Read-only; hits public EBI (BioStudies/MGnify/PRIDE/MetaboLights) and NCBI (GEO E-utils)
  endpoints, so responses depend on their uptime.
- PRIDE offers no public per-project protein-list API (`pride_search_project_proteins`
  returns pointers instead).
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
