#!/usr/bin/env python3
"""Research Resources MCP server — research support over PUBLIC APIs, no auth:

  * Grants.gov (api.grants.gov)              — federal funding opportunity search
  * Antibody Registry (antibodyregistry.org) — research antibody lookups (RRIDs)

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import requests
from mcp.server.fastmcp import FastMCP

GRANTS = "https://api.grants.gov/v1/api"
ABREG = "https://www.antibodyregistry.org/api"
HDRS = {"User-Agent": "Mozilla/5.0 Autogenesis-research/1.0", "Accept": "application/json"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("research_resources")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _post(url, body):
    r = requests.post(url, json=body, headers={**HDRS, "Content-Type": "application/json"}, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ================================================================= Grants.gov
@mcp.tool()
def search_grants(keyword: str, limit: int = 15) -> str:
    """Search Grants.gov federal funding opportunities by keyword.

    Args:
        keyword: search text (e.g. "cancer research", "microbiome").
        limit: max opportunities (default 15).
    Returns 'number<TAB>title<TAB>agency<TAB>status<TAB>closeDate' rows.
    """
    j = _post(f"{GRANTS}/search2", {"keyword": keyword, "rows": max(1, min(limit, MAX_ROWS))})
    data = j.get("data", {})
    hits = data.get("oppHits", []) if isinstance(data, dict) else []
    if not hits:
        return f"No funding opportunities for '{keyword}'."
    total = data.get("hitCount", len(hits)) if isinstance(data, dict) else len(hits)
    rows = [f"# {total} opportunities; showing {len(hits)}", "number\ttitle\tagency\tstatus\tcloseDate"]
    for h in hits:
        rows.append(f"{h.get('number','')}\t{(h.get('title') or '')[:60]}\t{(h.get('agency') or h.get('agencyCode') or '')[:30]}\t"
                    f"{h.get('oppStatus','')}\t{h.get('closeDate','')}")
    return _cap(rows, "opportunities")


# ============================================================ Antibody Registry
def _ab_row(a: dict) -> str:
    tgt = a.get("abTarget", "")
    sp = ", ".join(a.get("targetSpecies") or []) if isinstance(a.get("targetSpecies"), list) else (a.get("targetSpecies") or "")
    return (f"AB_{a.get('abId','')}\t{(a.get('abName') or '')[:45]}\t{a.get('vendorName','')}\t"
            f"{a.get('catalogNum','')}\t{tgt}\t{sp}")


@mcp.tool()
def search_antibodies(query: str, limit: int = 15) -> str:
    """Search the Antibody Registry (full-text) for research antibodies.

    Args:
        query: search text (e.g. "anti-GFP", "CD3 monoclonal").
        limit: max antibodies (default 15).
    Returns 'RRID<TAB>name<TAB>vendor<TAB>catalog<TAB>target<TAB>species' rows.
    """
    j = _get(f"{ABREG}/fts-antibodies", q=query, page=1, size=max(1, min(limit, MAX_ROWS)))
    items = j.get("items", []) if isinstance(j, dict) else []
    if not items:
        return f"No antibodies for '{query}'."
    rows = [f"# {j.get('totalElements','?')} antibodies; showing {len(items)}",
            "RRID\tname\tvendor\tcatalog\ttarget\tspecies"]
    rows += [_ab_row(a) for a in items]
    return _cap(rows, "antibodies")


@mcp.tool()
def get_antibody(antibody_id: str) -> str:
    """Get an antibody's details from the Antibody Registry by its id/RRID.

    Args:
        antibody_id: numeric abId (e.g. "3751761") or RRID (e.g. "AB_2532057").
    """
    aid = antibody_id.replace("AB_", "").strip()
    data = _get(f"{ABREG}/antibodies/{aid}")
    a = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
    if not a:
        return f"No antibody {antibody_id}."
    sp = ", ".join(a.get("targetSpecies") or []) if isinstance(a.get("targetSpecies"), list) else (a.get("targetSpecies") or "")
    return (f"RRID: AB_{a.get('abId','')}\nname: {a.get('abName','')}\nvendor: {a.get('vendorName','')}\n"
            f"catalog: {a.get('catalogNum','')}\ntarget: {a.get('abTarget','')}\nspecies: {sp}\n"
            f"clonality: {a.get('clonality','')}\nclone_id: {a.get('cloneId','')}\n"
            f"conjugate: {a.get('productConjugate','')}\ncitation: {(a.get('definingCitation') or '')[:120]}")


@mcp.tool()
def find_antibodies_by_catalog(catalog_number: str, limit: int = 15) -> str:
    """Find antibodies by vendor catalog number (via Antibody Registry full-text search).

    Args:
        catalog_number: vendor catalog number (e.g. "ab290").
        limit: max matches (default 15).
    """
    j = _get(f"{ABREG}/fts-antibodies", q=catalog_number, page=1, size=max(1, min(limit, MAX_ROWS)))
    items = j.get("items", []) if isinstance(j, dict) else []
    cat = catalog_number.lower().strip()
    exact = [a for a in items if cat in (a.get("catalogNum", "") or "").lower()]
    use = exact or items
    if not use:
        return f"No antibodies with catalog '{catalog_number}'."
    note = "" if exact else " (no exact catalog match; showing full-text hits)"
    rows = [f"# {len(use)} matches for catalog '{catalog_number}'{note}",
            "RRID\tname\tvendor\tcatalog\ttarget\tspecies"]
    rows += [_ab_row(a) for a in use]
    return _cap(rows, "antibodies")


@mcp.tool()
def get_antibody_registry_stats() -> str:
    """Get Antibody Registry summary statistics (total antibodies, last update)."""
    d = _get(f"{ABREG}/datainfo")
    return f"total_antibodies: {d.get('total','')}\nlast_update: {d.get('lastupdate','')}"


if __name__ == "__main__":
    mcp.run()
