---
name: protein_annotation_connector
description: Protein annotation via EBI InterPro (InterPro entries, domain architecture, Pfam clans & families), the Human Protein Atlas (per-gene records, tissue/subcellular search), and STRING (protein-protein interaction networks, homology). Public APIs, no auth.
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
  - search_interpro_entries
  - get_interpro_entry
  - get_domain_architecture
  - search_pfam_clans
  - get_pfam_clan
  - get_pfam_family_proteins
  - get_pfam_family_proteomes
  - get_protein_atlas_gene
  - search_protein_atlas
  - map_string_ids
  - get_string_network
  - get_string_similarity_scores
  - get_string_best_similarity_hits
---

# Protein Annotation

A self-contained MCP connector for protein domains, families, tissue expression and
interaction networks over three **public** APIs (no authentication):

- **EBI InterPro** (`www.ebi.ac.uk/interpro/api`) — InterPro entries and Pfam
  clans/families (Pfam is integrated into InterPro).
- **Human Protein Atlas** (`www.proteinatlas.org`) — per-gene records and search over
  tissue/subcellular expression columns.
- **STRING** (`string-db.org`) — protein-protein interaction networks and homology.

## Tools

### InterPro / Pfam
- `search_interpro_entries` — search entries (domains/families/sites) by keyword. Args: `query`, `limit`.
- `get_interpro_entry` — entry details: type, GO terms, member DBs, description. Args: `interpro_id`.
- `get_domain_architecture` — all InterPro/member entries on a protein. Args: `uniprot`, `limit`.
- `search_pfam_clans` — search/list Pfam clans (superfamilies). Args: `query`, `limit`.
- `get_pfam_clan` — clan details. Args: `clan_id` (e.g. "CL0001").
- `get_pfam_family_proteins` — UniProt proteins containing a Pfam family. Args: `pfam_id` (e.g. "PF00069"), `limit`.
- `get_pfam_family_proteomes` — proteomes (organisms) containing a Pfam family. Args: `pfam_id`, `limit`.

### Human Protein Atlas
- `get_protein_atlas_gene` — single-gene HPA record (identity, protein class, RNA/protein tissue specificity, subcellular location). Args: `gene` (Ensembl id or symbol).
- `search_protein_atlas` — search HPA and download selected columns. Args: `query`, `columns` (HPA column codes), `limit`.

### STRING
- `map_string_ids` — map gene symbols to STRING protein ids. Args: `genes` (list), `species`.
- `get_string_network` — interaction network for a gene set. Args: `genes` (list), `species`, `required_score`.
- `get_string_similarity_scores` — all-vs-all homology bit-scores within a gene set. Args: `genes` (list), `species`.
- `get_string_best_similarity_hits` — each protein's best homolog in target species. Args: `genes` (list), `species`, `species_b`.

## Typical workflow

1. `search_interpro_entries` → `get_interpro_entry`; `get_domain_architecture` for a specific protein.
2. `search_pfam_clans` / `get_pfam_clan`; `get_pfam_family_proteins` / `get_pfam_family_proteomes`.
3. `get_protein_atlas_gene` / `search_protein_atlas` for tissue expression and localization.
4. `map_string_ids` → `get_string_network` for interactions; `get_string_similarity_scores` /
   `get_string_best_similarity_hits` for within-set and cross-species homology.

## Notes

- Read-only; hits the public InterPro, Human Protein Atlas and STRING APIs, so responses
  depend on their uptime. STRING uses POST with a `caller_identity`; HPA search uses its
  `search_download.php` column codes (see proteinatlas.org for the full list).
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
