---
name: regulation_connector
description: Gene regulation — ENCODE experiments/files/biosamples, JASPAR transcription-factor binding matrices, UniBind TFBS datasets. Public APIs, no auth.
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
  - encode_search_experiments
  - encode_search_biosamples
  - encode_list_files
  - encode_get_experiment
  - encode_get_file
  - encode_get_biosample
  - jaspar_get_matrix
  - jaspar_matrix_versions
  - jaspar_list_matrices
  - jaspar_list_species
  - jaspar_list_taxa
  - jaspar_list_collections
  - jaspar_list_releases
  - unibind_search_tfbs
  - unibind_get_dataset
  - unibind_tfbs_in_region
---

# Regulation

A self-contained MCP connector for gene-regulation resources over **public** APIs
(no authentication): **ENCODE**, **JASPAR**, and **UniBind**.

## Tools

### ENCODE
- `encode_search_experiments` / `encode_search_biosamples` — search by keyword.
- `encode_list_files` — files of an experiment. Args: `experiment_accession`.
- `encode_get_experiment` / `encode_get_file` / `encode_get_biosample` — by accession.

### JASPAR (TF binding matrices)
- `jaspar_get_matrix` — matrix by id (e.g. "MA0139.1"). `jaspar_matrix_versions` — versions of a base id.
- `jaspar_list_matrices` — list/search matrices (by keyword / collection).
- `jaspar_list_species` / `jaspar_list_taxa` / `jaspar_list_collections` / `jaspar_list_releases`.

### UniBind (TFBS)
- `unibind_search_tfbs` — TFBS datasets by TF. Args: `tf`.
- `unibind_get_dataset` — dataset metadata. Args: `dataset_id`.
- `unibind_tfbs_in_region` — region-based lookup (pointers only; UniBind has no public
  per-region JSON API — region tracks are BED downloads).

## Typical workflow

1. `jaspar_list_matrices` / `jaspar_get_matrix` for a TF's binding motif.
2. `encode_search_experiments` → `encode_list_files` / `encode_get_file` for ChIP-seq data.
3. `unibind_search_tfbs` → `unibind_get_dataset` for curated TF binding-site datasets.

## Notes

- Read-only; hits public ENCODE / JASPAR / UniBind APIs, so responses depend on their uptime.
- `unibind_tfbs_in_region` returns download pointers (no public per-region JSON API exists).
  (The Claude Science original also lists UCSC Genome Browser as a region backend; UCSC is not
  reachable from this build environment, so region queries are pointer-only here.)
- The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
