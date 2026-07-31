#!/usr/bin/env python3
"""ZINC22 MCP server — purchasable ("make-on-demand" + in-stock) chemical space over
the PUBLIC CartBlanche22 API (https://cartblanche22.docking.org), no auth.

CartBlanche22 is the search front-end for ZINC22. Its substance/SMILES/supplier
searches are asynchronous: a POST returns a task id, and the results are polled from
`/search/result/<task>.json`. This server wraps that flow plus random sampling and
3D structure location.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import time
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

# CartBlanche22 API backend (the cartblanche.docking.org site is a SPA in front of it).
BASE = "https://cartblanche22.docking.org"
# ZINC22 pre-computed 3D structures (db2/mol2) are laid out by tranche here.
FILES = "https://files.docking.org"
HDRS = {"User-Agent": "Autogenesis-zinc/1.0", "Accept": "application/json"}
TIMEOUT = 60
MAX_ROWS = 60
POLL_TRIES = 25
POLL_DELAY = 3

mcp = FastMCP("zinc")


def _post(path: str, data: dict) -> requests.Response:
    r = requests.post(f"{BASE}{path}", data=data, headers={"User-Agent": HDRS["User-Agent"]},
                      timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"CartBlanche {path} -> {r.status_code}: {r.text[:200]}")
    return r


def _poll(task: str) -> list[dict]:
    """Poll a CartBlanche search task until it yields substance records (or gives up).

    The result endpoint returns a JSON list; while a search is still running (or found
    nothing) it returns an empty list or a list of empty strings.
    """
    url = f"{BASE}/search/result/{task}.json"
    for _ in range(POLL_TRIES):
        try:
            r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
        except requests.RequestException:
            time.sleep(POLL_DELAY)
            continue
        if r.status_code >= 400:
            time.sleep(POLL_DELAY)
            continue
        try:
            j = r.json()
        except ValueError:
            time.sleep(POLL_DELAY)
            continue
        if isinstance(j, dict):
            j = j.get("results") or j.get("substances") or []
        rows = [x for x in j if isinstance(x, dict)]
        if rows:
            return rows
        time.sleep(POLL_DELAY)
    return []


def _run_search(path: str, data: dict) -> list[dict]:
    """POST a search; follow the async task if one is returned, else use the direct rows."""
    r = _post(path, data)
    try:
        j = r.json()
    except ValueError:
        return []
    if isinstance(j, dict) and j.get("task"):
        return _poll(j["task"])
    if isinstance(j, dict):
        j = j.get("results") or j.get("substances") or []
    return [x for x in j if isinstance(x, dict)] if isinstance(j, list) else []


def _f(d: dict, *names):
    """Read a substance field tolerant of CartBlanche's varying key names."""
    for n in names:
        if d.get(n) not in (None, ""):
            return d[n]
    return ""


def _suppliers(d: dict) -> str:
    cats = d.get("catalogs") or d.get("catalog") or []
    if isinstance(cats, list):
        out = []
        for c in cats:
            if isinstance(c, dict):
                title = c.get("catalog_title") or c.get("catalog") or ""
                code = c.get("supplier_code", "")
                out.append(f"{title}:{code}" if title else str(code))
            else:
                out.append(str(c))
        return "; ".join(out[:6])
    return str(cats)


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _fmt_substances(recs: list[dict], header: str) -> str:
    rows = [header, "zinc_id\tsmiles\tsuppliers"]
    for d in recs:
        smi = _f(d, "smiles", "smile")
        rows.append(f"{_f(d,'zinc_id','sub_id')}\t{smi[:60]}\t{_suppliers(d)}")
    return _cap(rows, "substances")


@mcp.tool()
def zinc_search_by_id(zinc_ids: list[str]) -> str:
    """Look up purchasable ZINC22 compounds by ZINC id, with their supplier catalogs.

    Args:
        zinc_ids: one or more ZINC ids (e.g. ["ZINC000000000053"]).
    Returns each substance's SMILES and the supplier catalog/codes offering it.
    """
    ids = "\n".join(z.strip() for z in zinc_ids if z.strip())
    recs = _run_search("/substances.json", {"zinc_id": ids, "output_fields": "zinc_id,smiles,catalogs"})
    if not recs:
        return f"No ZINC22 substances found for {zinc_ids} (or the search is still processing)."
    return _fmt_substances(recs, f"# ZINC22 substances for {len(zinc_ids)} id(s)")


@mcp.tool()
def zinc_search_by_smiles(smiles: str, distance: int = 0, anonymous_distance: int = 0) -> str:
    """Search purchasable ZINC22 compounds by SMILES — exact or similarity search.

    Args:
        smiles: query SMILES (e.g. "c1ccc(cc1)C(=O)O").
        distance: SMILES/ECFP graph distance for similarity; 0 = exact match, higher = fuzzier.
        anonymous_distance: element-anonymized graph distance (0 = off); relaxes atom identity.
    Returns matching purchasable substances with SMILES and suppliers.
    """
    recs = _run_search("/smiles.json", {"smiles": smiles, "dist": str(max(0, distance)),
                                        "adist": str(max(0, anonymous_distance))})
    if not recs:
        return (f"No purchasable ZINC22 matches for '{smiles}' "
                f"(dist={distance}, adist={anonymous_distance}); or the search is still processing.")
    return _fmt_substances(recs, f"# ZINC22 SMILES search '{smiles}' (dist={distance}, adist={anonymous_distance})")


@mcp.tool()
def zinc_search_by_supplier(supplier_codes: list[str]) -> str:
    """Resolve supplier catalog numbers to ZINC22 substances.

    Args:
        supplier_codes: vendor catalog numbers / supplier codes to look up.
    Returns the ZINC substances that map to those catalog entries.
    """
    codes = "\n".join(c.strip() for c in supplier_codes if c.strip())
    recs = _run_search("/catitems.json", {"supplier_code": codes, "output_fields": "zinc_id,smiles,catalogs"})
    if not recs:
        return f"No ZINC22 substances resolved for supplier codes {supplier_codes}."
    return _fmt_substances(recs, f"# ZINC22 substances for {len(supplier_codes)} supplier code(s)")


@mcp.tool()
def zinc_random_sample(count: int = 10) -> str:
    """Draw a random sample of purchasable ZINC22 substances.

    Args:
        count: number of random substances to return (default 10, capped at 60).
    """
    n = max(1, min(count, MAX_ROWS))
    # The random endpoint returns a plain-text list of ZINC ids (optionally with SMILES).
    r = requests.get(f"{BASE}/substance/random.txt", params={"count": n},
                     headers={"User-Agent": HDRS["User-Agent"]}, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"CartBlanche random -> {r.status_code}: {r.text[:150]}")
    lines = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.startswith("<")]
    if not lines:
        return "CartBlanche returned no random substances (try again)."
    rows = [f"# {len(lines)} random ZINC22 substances"]
    rows += lines[:n]
    return _cap(rows, "substances")


@mcp.tool()
def zinc_get_3d(zinc_id: str) -> str:
    """Locate the docking-ready 3D structure of a ZINC22 compound.

    ZINC22 stores pre-generated 3D conformers (db2/mol2) organized by tranche. This
    returns the substance's tranche and the corresponding files.docking.org location,
    plus its ZINC page, so the 3D structure can be downloaded for docking.

    Args:
        zinc_id: ZINC id (e.g. "ZINC000000000053").
    """
    recs = _run_search("/substances.json",
                       {"zinc_id": zinc_id.strip(),
                        "output_fields": "zinc_id,smiles,tranche_name,sub_id,catalogs"})
    if not recs:
        return f"No ZINC22 substance {zinc_id} (or the search is still processing)."
    d = recs[0]
    tranche = _f(d, "tranche_name", "tranche")
    out = [f"# 3D structure location for {_f(d,'zinc_id','sub_id') or zinc_id}",
           f"smiles: {_f(d,'smiles','smile')}",
           f"tranche: {tranche or '(not reported)'}",
           f"zinc_page: https://zinc.docking.org/substances/{zinc_id}/"]
    if tranche:
        out.append(f"3d_tranche_dir: {FILES}/3D/{tranche}/")
    out.append("Download db2/mol2 conformers from the 3D tranche directory (see "
               "wiki.docking.org/index.php/ZINC22:Downloading).")
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
