---
name: clinical_genomics_connector
description: Clinical genomics knowledge — ClinGen gene validity/dosage/variant curations, CIViC clinical evidence & assertions, Open Targets target/disease/drug associations. Aggregates three public sources (no auth).
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
  - clingen_gene_validity
  - clingen_dosage_sensitivity
  - clingen_actionability
  - clingen_variant_classifications
  - civic_search_genes
  - civic_gene_variants
  - civic_get_variant
  - civic_search_variants
  - civic_get_molecular_profile
  - civic_search_molecular_profiles
  - civic_get_evidence_item
  - civic_search_evidence
  - civic_get_assertion
  - civic_search_assertions
  - civic_search_diseases
  - civic_search_therapies
  - open_targets_graphql
  - open_targets_disease_targets
  - open_targets_disease_drugs
  - open_targets_drug
---

# Clinical Genomics

A self-contained MCP connector aggregating three **public** clinical-genomics resources
(no authentication): **ClinGen**, **CIViC**, and **Open Targets**.

## Tools

### ClinGen — gene/variant curations
- `clingen_gene_validity` — gene-disease validity classifications. Args: `gene`.
- `clingen_dosage_sensitivity` — haploinsufficiency / triplosensitivity. Args: `gene`.
- `clingen_variant_classifications` — Evidence Repository variant interpretations. Args: `gene`, `limit`.
- `clingen_actionability` — actionability report link (no public JSON API). Args: `gene`.

### CIViC — clinical interpretation of variants (GraphQL)
- `civic_search_genes` — gene by symbol → CIViC id + description. Args: `symbol`.
- `civic_gene_variants` — variants curated for a gene. Args: `gene`, `limit`.
- `civic_get_variant` — variant details. Args: `variant_id`.
- `civic_search_variants` — variants by name (e.g. "V600E"). Args: `query`, `limit`.
- `civic_get_molecular_profile` / `civic_search_molecular_profiles` — molecular profiles. Args: `molecular_profile_id` / `query`.
- `civic_get_evidence_item` / `civic_search_evidence` — clinical evidence (by id / disease). Args: `evidence_id` / `disease`.
- `civic_get_assertion` / `civic_search_assertions` — summarized assertions. Args: `assertion_id` / `disease`.
- `civic_search_diseases` — diseases by name. Args: `query`.
- `civic_search_therapies` — therapies/drugs by name. Args: `query`.

### Open Targets — target/disease/drug associations (GraphQL)
- `open_targets_graphql` — arbitrary GraphQL passthrough. Args: `query`, `variables` (JSON string).
- `open_targets_disease_targets` — targets associated with a disease (scored). Args: `disease`, `limit`.
- `open_targets_disease_drugs` — drugs/clinical candidates for a disease. Args: `disease`, `limit`.
- `open_targets_drug` — drug type, phase, mechanism, indications. Args: `drug` (name or ChEMBL id).

Gene args accept HGNC symbols; Open Targets args accept names or ontology ids
(ENSG / EFO / MONDO / CHEMBL), auto-resolved via Open Targets search.

## Typical workflow

1. `civic_search_genes` / `clingen_gene_validity` for a gene's clinical validity & interpretations.
2. `civic_search_variants` → `civic_get_variant` → `civic_search_evidence` / `civic_get_assertion`
   for variant-level clinical evidence and therapy implications.
3. `clingen_dosage_sensitivity` / `clingen_variant_classifications` for dosage & variant pathogenicity.
4. `open_targets_disease_targets` / `open_targets_disease_drugs` / `open_targets_drug` for the
   target-disease-drug landscape; `open_targets_graphql` for anything else.

## Notes

- Read-only; hits public ClinGen (FTP/ERepo), CIViC (GraphQL), and Open Targets (GraphQL)
  endpoints, so responses depend on their uptime. ClinGen actionability has no public API.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
