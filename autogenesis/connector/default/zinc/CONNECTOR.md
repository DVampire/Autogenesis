---
name: zinc_connector
description: ZINC22 purchasable chemical space via CartBlanche22 — look up compounds by ZINC id, SMILES (exact/similarity) or supplier catalog number, draw random samples, and locate docking-ready 3D structures. Public API, no auth.
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
  - zinc_search_by_id
  - zinc_search_by_smiles
  - zinc_search_by_supplier
  - zinc_random_sample
  - zinc_get_3d
---

# ZINC22 (CartBlanche22)

A self-contained MCP connector over the **public** CartBlanche22 API
(`https://cartblanche22.docking.org`), the search front-end for **ZINC22** — Irwin &
Shoichet's catalog of purchasable ("make-on-demand" + in-stock) compounds used for
virtual screening and docking. No authentication.

CartBlanche's substance / SMILES / supplier searches are **asynchronous**: a POST
returns a task id and the results are polled from `/search/result/<task>.json`. This
connector wraps that task-and-poll flow so each tool call returns finished results.

## Tools

- `zinc_search_by_id` — look up compounds by ZINC id, with supplier catalogs. Args: `zinc_ids` (list).
- `zinc_search_by_smiles` — exact or similarity structure search. Args: `smiles`, `distance` (0 = exact), `anonymous_distance`.
- `zinc_search_by_supplier` — resolve supplier catalog numbers to ZINC substances. Args: `supplier_codes` (list).
- `zinc_random_sample` — random sample of purchasable substances. Args: `count`.
- `zinc_get_3d` — locate the docking-ready 3D structure (tranche + files.docking.org path). Args: `zinc_id`.

## Typical workflow

1. `zinc_search_by_smiles` (with a `distance` for analogs) or `zinc_search_by_id` to find
   purchasable compounds; `zinc_search_by_supplier` to go from a vendor catalog number to ZINC.
2. `zinc_get_3d` to locate the pre-generated 3D conformers for docking.
3. `zinc_random_sample` for a quick, unbiased sample of the purchasable space.

## Notes

- Read-only; hits the public CartBlanche22 API, so responses depend on its uptime. The
  search endpoints are asynchronous and can be slow — the tools poll for completion and
  will report if a search is still processing.
- 3D conformers (db2/mol2) are organized by tranche under `files.docking.org`; see
  wiki.docking.org (ZINC22:Downloading) for the tranche layout.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
