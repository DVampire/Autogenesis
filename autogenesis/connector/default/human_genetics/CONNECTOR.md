---
name: human_genetics_connector
description: Human genetics associations — GWAS Catalog variant/gene/trait associations & studies, eQTL Catalogue expression QTLs, and FinnGen/BioBank-Japan PheWAS. Public APIs, no auth.
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
  - gwas_associations_for_variant
  - gwas_associations_for_gene
  - gwas_associations_for_trait
  - gwas_search_traits
  - gwas_search_studies
  - gwas_get_study
  - gwas_get_variant
  - eqtl_list_datasets
  - eqtl_associations
  - phewas_instances
  - phewas_variant
  - phewas_finngen_gene
  - phewas_list_phenotypes
  - phewas_search_phenotypes
---

# Human Genetics

A self-contained MCP connector for human genetics associations, aggregating **public**
resources (no authentication): **GWAS Catalog** (EMBL-EBI), **eQTL Catalogue** (EMBL-EBI),
and **FinnGen** PheWAS (public r12 release). GWAS endpoint mappings are referenced from
the open-source [koido/gwas-catalog-mcp](https://github.com/koido/gwas-catalog-mcp) (Apache-2.0).

## Tools

### GWAS Catalog
- `gwas_associations_for_variant` — trait associations for an rsID. Args: `rsid`, `limit`.
- `gwas_associations_for_gene` — GWAS-cataloged variants mapped to a gene. Args: `gene`, `limit`.
- `gwas_associations_for_trait` — associations for a trait (name/EFO id). Args: `trait`, `limit`.
- `gwas_search_traits` — search EFO traits by name. Args: `query`.
- `gwas_search_studies` — studies by disease/trait. Args: `disease_trait`, `limit`.
- `gwas_get_study` — study by accession. Args: `accession`.
- `gwas_get_variant` — SNP record by rsID. Args: `rsid`.

### eQTL Catalogue
- `eqtl_list_datasets` — QTL datasets (filter by quant method / tissue). Args: `quant_method`, `tissue`, `limit`.
- `eqtl_associations` — associations in a dataset for a gene/region. Args: `dataset_id`, `gene`, `region`, `limit`.

### PheWAS
- `phewas_instances` — list PheWAS portals (FinnGen, BioBank Japan). No args.
- `phewas_variant` — phenome-wide associations for a variant (via GWAS Catalog). Args: `rsid`, `limit`.
- `phewas_finngen_gene` — gene-based PheWAS in FinnGen. Args: `gene`, `limit`.
- `phewas_list_phenotypes` — phenotypes in a PheWAS instance. Args: `instance`, `limit`.
- `phewas_search_phenotypes` — search phenotypes by name/category. Args: `query`, `instance`, `limit`.

## Typical workflow

1. `gwas_search_traits` / `gwas_search_studies` to scope a trait; `gwas_associations_for_gene`
   / `gwas_get_variant` for a gene/variant.
2. `eqtl_list_datasets` → `eqtl_associations` for the regulatory (expression) effect of variants.
3. `phewas_finngen_gene` / `phewas_variant` for phenome-wide effects; `phewas_search_phenotypes`
   to find a phenotype code.

## Notes

- Read-only; hits public GWAS Catalog / eQTL Catalogue / FinnGen (r12) endpoints, so responses
  depend on their uptime.
- `gwas_associations_for_variant`, `gwas_associations_for_trait`, and `phewas_variant` use the
  GWAS Catalog *associations* endpoint, which can be **slow for highly-associated variants/traits**
  (e.g. APOE rs429358) — they time out gracefully with a hint if so. The other 11 tools are fast.
- PheWAS phenotype/gene tools use FinnGen's public r12 API. BioBank Japan (pheweb.jp) is listed as
  an instance but exposes only a limited public API.
- The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
