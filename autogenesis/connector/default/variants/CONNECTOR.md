---
name: variants_connector
description: Human genetic variants — gnomAD population frequencies/constraint (r4), ClinVar records/search (direct NCBI), dbSNP, structural and mitochondrial variants. Public APIs, no auth.
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
  - get_variant
  - search_variants
  - gene_variants
  - gene_constraint
  - region_variants
  - liftover_variant
  - structural_variants
  - get_structural_variant
  - mitochondrial_variants
  - clinvar_variants
  - clinvar_search
  - clinvar_get_records
  - clinvar_variant_by_rsid
  - dbsnp_get_rsids
  - dbsnp_search_by_region
---

# Variants

A self-contained MCP connector for human genetic variants over **public** APIs
(no authentication): **gnomAD** (GraphQL), **ClinVar** and **dbSNP** (NCBI E-utilities).

## Tools

### gnomAD (population frequencies & constraint, r4)
- `get_variant` (by id) / `search_variants` / `gene_variants` (by gene) / `region_variants`.
- `gene_constraint` (pLI, o/e LoF & missense). `liftover_variant` (GRCh37↔38).
- `structural_variants` / `get_structural_variant`. `mitochondrial_variants`.

### ClinVar (clinical significance, NCBI)
- `clinvar_variants` (by gene) / `clinvar_search` (free text) / `clinvar_get_records` (by id) /
  `clinvar_variant_by_rsid`.

### dbSNP (NCBI)
- `dbsnp_get_rsids` (alleles, MAF, clinical sig, genes) / `dbsnp_search_by_region`.

## Typical workflow

1. `dbsnp_get_rsids` / `get_variant` for a specific variant; `clinvar_variant_by_rsid` for its
   clinical significance.
2. `gene_variants` / `gene_constraint` for a gene's variation and tolerance; `region_variants`
   / `dbsnp_search_by_region` for a locus.

## Notes

- Read-only; ClinVar/dbSNP hit NCBI E-utilities (rate-limited ~3 req/s; the connector retries on 429).
- The **gnomAD** API is 403-blocked from some networks (including this build sandbox). The gnomAD
  tools follow the official gnomAD GraphQL schema and work where the API is reachable; they degrade
  gracefully with a clear message otherwise. ClinVar/dbSNP tools are verified.
- The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
