---
name: structures_interactions_connector
description: Structures and molecular interactions — RCSB PDB structures, AlphaFold predictions, EMDB cryo-EM entries, Complex Portal complexes, IntAct interaction networks. Public APIs, no auth.
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
  - pdb_search_structures
  - pdb_get_structures
  - pdb_get_entities
  - pdb_get_ligands
  - alphafold_get_prediction
  - alphafold_check_coverage
  - emdb_search_entries
  - emdb_get_entries
  - emdb_get_entry_section
  - emdb_get_validation
  - complexportal_get_complexes
  - complexportal_search_by_participant
  - intact_fetch_interactions
  - intact_get_interactor
  - intact_get_interaction_details
  - intact_build_network
---

# Structures & Interactions

A self-contained MCP connector for macromolecular structures and molecular interactions,
over **public** APIs (no authentication): **RCSB PDB**, **AlphaFold**, **EMDB**,
**Complex Portal**, and **IntAct**. PDB/AlphaFold endpoint mappings referenced from the
open-source [cyanheads/protein-mcp-server](https://github.com/cyanheads/protein-mcp-server).

## Tools

### RCSB PDB (experimental structures)
- `pdb_search_structures` — full-text search. `pdb_get_structures` — entry metadata.
- `pdb_get_entities` — polymer chains. `pdb_get_ligands` — non-polymer ligands.

### AlphaFold (predicted structures)
- `alphafold_get_prediction` — model + mean pLDDT for a UniProt accession.
- `alphafold_check_coverage` — whether a prediction exists and its residue coverage.

### EMDB (cryo-EM)
- `emdb_search_entries` / `emdb_get_entries` (summary + resolution).
- `emdb_get_entry_section` — a named section of the record. `emdb_get_validation` — processing/resolution summary.

### Complex Portal (curated complexes)
- `complexportal_get_complexes` (by name/accession) / `complexportal_search_by_participant`.

### IntAct (interaction networks)
- `intact_fetch_interactions` / `intact_get_interactor` / `intact_get_interaction_details` /
  `intact_build_network` (nodes + edges).

## Typical workflow

1. `pdb_search_structures` → `pdb_get_structures` / `pdb_get_entities` / `pdb_get_ligands`
   for experimental structures; `alphafold_get_prediction` for a predicted model; `emdb_*` for cryo-EM maps.
2. `complexportal_search_by_participant` for a protein's complexes; `intact_fetch_interactions`
   / `intact_build_network` for its interaction network.

## Notes

- Read-only; hits public RCSB / AlphaFold / EMDB / Complex Portal / IntAct APIs, so responses
  depend on their uptime.
- `emdb_get_validation` summarizes processing/resolution (EMDB serves full validation reports as
  PDFs). The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
