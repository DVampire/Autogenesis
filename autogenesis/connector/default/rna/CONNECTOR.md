---
name: rna_connector
description: RNA families via Rfam — family metadata, seed alignments, covariance models, phylogenetic trees, PDB structure mappings, accession/id conversion, and sequence search. Public API, no auth.
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
  - get_family
  - get_seed_alignment
  - get_covariance_model
  - get_tree
  - get_sequence_regions
  - get_structure_mapping
  - accession_to_id
  - id_to_accession
  - search_sequence
---

# RNA

A self-contained MCP connector for RNA families over the **public** Rfam API
(`rfam.org`), no authentication. Rfam represents RNA families by multiple-sequence
alignments, consensus secondary structures, and covariance models.

## Tools

- `get_family` — family metadata (id, description, clan, curation). Args: `accession`.
- `get_seed_alignment` — seed alignment (Stockholm, truncated). Args: `accession`.
- `get_covariance_model` — covariance model (CM) header (truncated). Args: `accession`.
- `get_tree` — phylogenetic tree (Newick, truncated). Args: `accession`.
- `get_structure_mapping` — CM-to-PDB 3D structure mappings. Args: `accession`, `limit`.
- `accession_to_id` / `id_to_accession` — convert between accession (RF…) and family id.
- `get_sequence_regions` — genomic regions of a family (pointer to FTP; Rfam restricts the
  full-region web API).
- `search_sequence` — scan a nucleotide sequence against Rfam CMs (Infernal cmscan, async).

## Typical workflow

1. `get_family` (or `id_to_accession`) to identify a family; `get_structure_mapping` for its
   solved 3D structures.
2. `get_seed_alignment` / `get_covariance_model` / `get_tree` for the family's models.
3. `search_sequence` to classify an unknown RNA sequence into an Rfam family.

## Notes

- Read-only; hits the public Rfam API, so responses depend on its uptime.
- `get_sequence_regions` returns an FTP pointer (Rfam does not serve full regions over the web
  API); `search_sequence` uses Rfam's async cmscan service, which can be rate-limited (the tool
  degrades gracefully with a hint when it is unavailable).
- The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
