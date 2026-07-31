---
name: cbioportal_connector
description: Cancer genomics cohorts — cBioPortal studies, mutations, copy-number alterations, and clinical attributes, over the public cBioPortal REST API (no auth).
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
  - cbioportal_list_studies
  - cbioportal_get_study
  - cbioportal_mutations_in_gene
  - cbioportal_mutation_frequency
  - cbioportal_cna_in_gene
  - cbioportal_clinical_attributes
---

# Cancer Models (cBioPortal)

A self-contained MCP connector over the **public** cBioPortal REST API
(`https://www.cbioportal.org/api`). No authentication. Explore cancer genomics
cohorts: studies, somatic mutations, copy-number alterations, and clinical
attributes. Gene arguments accept either a Hugo symbol (e.g. `TP53`) or an Entrez
ID; molecular-profile and sample-list IDs are resolved automatically per study.

## Tools

### cbioportal_list_studies
List cancer studies (cohorts), optionally filtered by keyword.
- `keyword` (str, optional, e.g. "glioblastoma", "breast", "tcga"), `limit` (int, optional).

### cbioportal_get_study
Metadata for one study (name, cancer type, sample count, citation).
- `study_id` (str, e.g. `gbm_tcga_pan_can_atlas_2018`).

### cbioportal_mutations_in_gene
List a gene's mutations across a study's samples.
- `study_id` (str), `gene` (str, symbol or Entrez), `sample_list_id` (str, optional; default `<study>_all`).

### cbioportal_mutation_frequency
Fraction of samples in a study mutated in a gene (mutated / total).
- `study_id` (str), `gene` (str), `sample_list_id` (str, optional).

### cbioportal_cna_in_gene
Discrete copy-number alterations of a gene across a study.
- `study_id` (str), `gene` (str), `event_type` (str, optional: ALL / AMP / HOMDEL /
  HOMDEL_AND_AMP / GAIN / HETLOSS / DIPLOID; default HOMDEL_AND_AMP).
  Alteration codes: -2 HOMDEL, -1 HETLOSS, 1 GAIN, 2 AMP.

### cbioportal_clinical_attributes
Clinical attributes recorded for a study's patients/samples.
- `study_id` (str).

## Typical workflow

1. `cbioportal_list_studies(keyword=...)` to find a cohort, then `cbioportal_get_study`
   for its details and sample count.
2. `cbioportal_mutation_frequency` / `cbioportal_mutations_in_gene` for somatic mutations,
   and `cbioportal_cna_in_gene` for amplifications/deletions of a gene of interest.
3. `cbioportal_clinical_attributes` to see what clinical variables are available for
   correlation.

## Notes

- Read-only; hits the public cBioPortal API, so responses depend on its uptime.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
