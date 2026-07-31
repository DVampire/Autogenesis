---
name: chembl_connector
description: EMBL-EBI ChEMBL database (v34) — search compounds, targets, bioactivity, mechanisms of action, approved drugs, and ADMET properties.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: streamable_http
  url: https://hcls.mcp.claude.com/chembl/mcp
actions:
  - compound_search
  - target_search
  - get_bioactivity
  - get_mechanism
  - drug_search
  - get_admet
---

# ChEMBL

An MCP connector for the manually curated ChEMBL database of bioactive, drug-like small
molecules. Supports drug-discovery research: compound screening, target identification,
mechanism analysis, and pharmacokinetic/safety profiling.

## Tools

### compound_search
Find compounds by name, SMILES, or ChEMBL ID. Starting point for compound analysis.

### target_search
Find biological targets (proteins, genes, receptors) by gene symbol or protein name.

### get_bioactivity
Retrieve quantitative activity data (IC50, EC50, Ki) for compound–target pairs.

### get_mechanism
Get a drug's mechanism of action and its primary target binding.

### drug_search
Find approved drugs by name or indication, for therapeutic-landscape analysis.

### get_admet
Retrieve ADMET (absorption, distribution, metabolism, excretion, toxicity) properties.

## Typical workflow

1. `compound_search` or `drug_search` to identify the compound of interest.
2. `get_mechanism` to understand how it works and its primary targets.
3. `target_search` for detailed target information.
4. `get_bioactivity` for quantitative binding/activity data.
5. `get_admet` for pharmacokinetic properties.
