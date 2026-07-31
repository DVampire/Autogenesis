#!/usr/bin/env python3
"""CellGuide MCP server — a self-contained wrapper over the PUBLIC CZ CELLxGENE
CellGuide data (https://cellguide.cellxgene.cziscience.com, CC-BY-4.0).

Cell-type information: descriptions, marker genes, tissue distribution, and the
source datasets/collections. No authentication — reads the published CellGuide
JSON snapshot.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from typing import Optional, Tuple

import requests
from mcp.server.fastmcp import FastMCP

CG = "https://cellguide.cellxgene.cziscience.com"
TIMEOUT = 45
MAX_ROWS = 100

mcp = FastMCP("cellguide")

_cache: dict = {}


# --------------------------------------------------------------------------- #
# Data access (snapshot + cached metadata)
# --------------------------------------------------------------------------- #
def _snapshot() -> str:
    if "snap" not in _cache:
        r = requests.get(f"{CG}/latest_snapshot_identifier", timeout=TIMEOUT)
        r.raise_for_status()
        _cache["snap"] = r.text.strip()
    return _cache["snap"]


def _cg_json(path: str):
    r = requests.get(f"{CG}/{_snapshot()}/{path}", timeout=TIMEOUT,
                     headers={"User-Agent": "Autogenesis-cellguide/1.0"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _metadata() -> dict:
    if "meta" not in _cache:
        _cache["meta"] = _cg_json("celltype_metadata.json") or {}
    return _cache["meta"]


def _resolve(cell_type: str) -> Tuple[str, dict]:
    """Resolve a CL id ('CL:0000084'/'CL_0000084') or a name to (cl_id, metadata entry)."""
    meta = _metadata()
    ct = cell_type.strip()
    cl = ct.replace("_", ":") if ct.upper().startswith(("CL:", "CL_")) else None
    if cl:
        cl = "CL:" + cl.split(":", 1)[1]
        if cl in meta:
            return cl, meta[cl]
        raise RuntimeError(f"Cell type id '{cl}' not found in CellGuide.")
    low = ct.lower()
    exact = [(k, v) for k, v in meta.items() if v.get("name", "").lower() == low]
    if exact:
        return exact[0]
    partial = [(k, v) for k, v in meta.items()
               if low in v.get("name", "").lower()
               or any(low in s.lower() for s in v.get("synonyms", []) or [])]
    if partial:
        return partial[0]
    raise RuntimeError(f"No cell type matching '{cell_type}'. Try search_cell_types first.")


def _clfile(cl_id: str) -> str:
    return cl_id.replace(":", "_")


def _cap(rows: list[str], scope: str) -> str:
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def search_cell_types(query: str, limit: int = 25) -> str:
    """Search cell types by name or synonym (Cell Ontology).

    Args:
        query: text to match against cell-type names/synonyms (e.g. "T cell", "neuron").
        limit: max results (default 25).
    Returns 'CL_id<TAB>name' rows.
    """
    low = query.lower().strip()
    meta = _metadata()
    hits = []
    for k, v in meta.items():
        name = v.get("name", "")
        if low in name.lower() or any(low in s.lower() for s in v.get("synonyms", []) or []):
            hits.append((k, name))
    hits.sort(key=lambda kv: (low != kv[1].lower(), len(kv[1])))
    rows = ["CL_id\tname"] + [f"{k}\t{n}" for k, n in hits[:max(1, limit)]]
    return "\n".join(rows) if len(rows) > 1 else f"No cell types matching '{query}'."


@mcp.tool()
def get_cell_type_info(cell_type: str) -> str:
    """Get a cell type's canonical description and synonyms.

    Args:
        cell_type: a CL id (e.g. "CL:0000084") or a name (e.g. "T cell").
    """
    cl, v = _resolve(cell_type)
    syn = ", ".join(v.get("synonyms", []) or []) or "(none)"
    return (f"id: {cl}\nname: {v.get('name','')}\n"
            f"description: {v.get('clDescription','')}\nsynonyms: {syn}")


@mcp.tool()
def get_marker_genes(cell_type: str, kind: str = "canonical", limit: int = 50) -> str:
    """Get marker genes for a cell type.

    Args:
        cell_type: a CL id or name.
        kind: "canonical" (literature-curated, with tissue + publication) or
            "computational" (CELLxGENE-computed, ranked by marker_score).
        limit: max genes (default 50).
    """
    cl, _ = _resolve(cell_type)
    if kind == "computational":
        data = _cg_json(f"computational_marker_genes/{_clfile(cl)}.json") or []
        data.sort(key=lambda d: d.get("marker_score", 0), reverse=True)
        rows = ["symbol\tmarker_score\tspecificity\torganism"]
        for d in data[:max(1, limit)]:
            org = (d.get("groupby_dims") or {}).get("organism_ontology_term_label", "")
            rows.append(f"{d.get('symbol','')}\t{d.get('marker_score',0):.3f}\t{d.get('specificity',0):.2f}\t{org}")
    else:
        data = _cg_json(f"canonical_marker_genes/{_clfile(cl)}.json") or []
        rows = ["symbol\tname\ttissue"]
        for d in data[:max(1, limit)]:
            rows.append(f"{d.get('symbol','')}\t{d.get('name','')}\t{d.get('tissue','')}")
    if len(rows) == 1:
        return f"No {kind} marker genes for {cl}."
    return _cap(rows, "genes")


@mcp.tool()
def get_cell_tissues(cell_type: str) -> str:
    """List the tissues where a cell type is characterized (from its marker data).

    Args:
        cell_type: a CL id or name.
    Returns one tissue per line.
    """
    cl, _ = _resolve(cell_type)
    data = _cg_json(f"canonical_marker_genes/{_clfile(cl)}.json") or []
    tissues = sorted({d.get("tissue", "") for d in data if d.get("tissue")})
    if not tissues:
        return f"No tissue information available for {cl}."
    return f"{cl} — tissues:\n" + "\n".join(f"- {t}" for t in tissues)


@mcp.tool()
def get_source_data(cell_type: str, limit: int = 25) -> str:
    """List the source datasets/collections that describe a cell type.

    Args:
        cell_type: a CL id or name.
        limit: max collections (default 25).
    Returns 'collection_name<TAB>collection_url<TAB>publication_url' rows.
    """
    cl, _ = _resolve(cell_type)
    data = _cg_json(f"source_collections/{_clfile(cl)}.json") or []
    seen, rows = set(), ["collection_name\tcollection_url\tpublication_url"]
    for d in data:
        url = d.get("collection_url", "")
        if url in seen:
            continue
        seen.add(url)
        rows.append(f"{d.get('collection_name','')}\t{url}\t{d.get('publication_url','')}")
        if len(rows) > limit:
            break
    if len(rows) == 1:
        return f"No source collections for {cl}."
    return _cap(rows, "collections")


if __name__ == "__main__":
    mcp.run()
