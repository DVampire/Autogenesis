---
name: chemistry_connector
description: Small-molecule chemistry — PubChem compounds/properties/similarity, ChEBI ontology, Rhea reactions, BindingDB affinities. Aggregates four public APIs (no auth).
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
  - pubchem_search_compounds
  - pubchem_get_compounds
  - pubchem_similarity_search
  - pubchem_get_bioassay_summary
  - pubchem_get_safety
  - chebi_search
  - chebi_get_entity
  - chebi_get_ontology
  - rhea_search_reactions
  - rhea_get_reaction
  - bindingdb_ligands_by_target
  - bindingdb_targets_by_compound
---

# Chemistry

A self-contained MCP connector for small-molecule chemistry, aggregating four
**public** APIs (no authentication): **PubChem** (PUG REST), **ChEBI** (via EBI OLS),
**Rhea** (rhea-db.org), and **BindingDB**.

## Tools

### PubChem — compounds, properties, similarity, bioassay, safety
- `pubchem_search_compounds` — search by name; returns CID, title, formula. Args: `query`, `limit`.
- `pubchem_get_compounds` — properties for CIDs. Args: `cids` (list[int]), `properties` (comma-separated PUG props, optional).
- `pubchem_similarity_search` — 2D-similarity by SMILES. Args: `smiles`, `threshold` (0-100), `limit`.
- `pubchem_get_bioassay_summary` — active/inactive counts + sample active assays. Args: `cid`.
- `pubchem_get_safety` — GHS classification (signal, hazard statements, pictograms). Args: `cid`.

### ChEBI — ontology (via EBI OLS)
- `chebi_search` — search entities by name. Args: `query`, `limit`.
- `chebi_get_entity` — definition + formula/mass/charge/SMILES/InChIKey. Args: `chebi_id` (e.g. `CHEBI:27732`).
- `chebi_get_ontology` — is_a parents and children. Args: `chebi_id`.

### Rhea — biochemical reactions
- `rhea_search_reactions` — search reactions by keyword/compound. Args: `query`, `limit`.
- `rhea_get_reaction` — equation, status, ChEBI participants. Args: `rhea_id` (e.g. `RHEA:10280`).

### BindingDB — binding affinities
- `bindingdb_ligands_by_target` — measured ligand affinities for a protein target, sorted by potency.
  Args: `uniprot` (e.g. `P00533`), `cutoff_nm` (default 100), `limit`.
- `bindingdb_targets_by_compound` — targets bound by compounds similar to a query molecule.
  Args: `smiles`, `similarity_cutoff` (Tanimoto, default 0.85), `limit`.

## Typical workflow

1. `pubchem_search_compounds` / `chebi_search` to identify a compound (CID / ChEBI id).
2. `pubchem_get_compounds` for physicochemical properties; `chebi_get_entity` for the
   ontology definition; `pubchem_get_safety` for GHS hazards.
3. `pubchem_similarity_search` for structural analogs.
4. `rhea_search_reactions` / `rhea_get_reaction` for the metabolic reactions a compound
   participates in; `bindingdb_ligands_by_target` for a target's potent binders, or
   `bindingdb_targets_by_compound` to find what a molecule's analogs bind.

## Notes

- Read-only; hits public PubChem/ChEBI(OLS)/Rhea/BindingDB endpoints, so responses depend
  on their uptime. BindingDB responses for well-studied targets can be large — use a tight
  `cutoff_nm`.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
