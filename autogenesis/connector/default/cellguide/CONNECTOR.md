---
name: cellguide_connector
description: Cell type information from CZ CELLxGENE CellGuide — descriptions, marker genes, tissue distribution, and source datasets. Public data (CC-BY-4.0), no auth.
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
  - search_cell_types
  - get_cell_type_info
  - get_marker_genes
  - get_cell_tissues
  - get_source_data
---

# CellGuide

A self-contained MCP connector over the **public** CZ CELLxGENE CellGuide data
(`https://cellguide.cellxgene.cziscience.com`, CC-BY-4.0). No authentication — it
reads the published CellGuide JSON snapshot. Look up cell types by name or Cell
Ontology (CL) id and retrieve descriptions, marker genes, tissue distribution, and
the source datasets that characterize them.

## Tools

### search_cell_types
Find cell types by name or synonym.
- `query` (str, e.g. "T cell", "neuron"), `limit` (int, optional).
- Returns `CL_id<TAB>name`.

### get_cell_type_info
Canonical description and synonyms for a cell type.
- `cell_type` (str: a CL id like `CL:0000084`, or a name like "T cell").

### get_marker_genes
Marker genes for a cell type.
- `cell_type` (str), `kind` (str: "canonical" — literature-curated with tissue +
  publication; or "computational" — CELLxGENE-computed, ranked by marker_score),
  `limit` (int, optional).

### get_cell_tissues
Tissues where the cell type is characterized (from its marker data).
- `cell_type` (str).

### get_source_data
Source datasets/collections describing the cell type (with CELLxGENE + publication links).
- `cell_type` (str), `limit` (int, optional).

## Typical workflow

1. `search_cell_types` to find the CL id for a cell type of interest.
2. `get_cell_type_info` for its definition; `get_marker_genes` for canonical or
   computational markers.
3. `get_cell_tissues` for tissue distribution and `get_source_data` for the
   underlying datasets/publications.

## Notes

- Read-only; reads the public CellGuide CDN snapshot (auto-resolved to latest).
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
