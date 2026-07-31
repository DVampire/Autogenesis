#!/usr/bin/env python3
"""Drug Regulatory MCP server — FDA drug data over the PUBLIC openFDA API
(https://api.fda.gov/drug), no auth. Drugs@FDA applications & approvals, pharmacologic
classes, generic equivalents, and SPL drug labels.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://api.fda.gov/drug"
HDRS = {"User-Agent": "Autogenesis-drugreg/1.0"}
TIMEOUT = 45
MAX_ROWS = 50

mcp = FastMCP("drug_regulatory")


def _get(path: str, **params):
    r = requests.get(f"{BASE}/{path}", params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code == 404:
        return {"results": []}          # openFDA returns 404 for "no matches"
    if r.status_code >= 400:
        raise RuntimeError(f"openFDA {path} -> {r.status_code}: {r.text[:200]}")
    return r.json()


def _name_query(q: str) -> str:
    """Match a drug name against brand OR generic name."""
    return f'openfda.brand_name:"{q}" openfda.generic_name:"{q}"'


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


@mcp.tool()
def search_drug_applications(query: str, limit: int = 10) -> str:
    """Search Drugs@FDA applications by brand or generic drug name.

    Args:
        query: brand or generic name (e.g. "atorvastatin", "Lipitor").
        limit: max applications (default 10).
    Returns 'application<TAB>sponsor<TAB>brand<TAB>generic' rows.
    """
    j = _get("drugsfda.json", search=_name_query(query), limit=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", [])
    if not res:
        return f"No Drugs@FDA applications for '{query}'."
    rows = ["application\tsponsor\tbrand\tgeneric"]
    for r in res:
        o = r.get("openfda", {})
        rows.append(f"{r.get('application_number','')}\t{r.get('sponsor_name','')}\t"
                    f"{(o.get('brand_name') or [''])[0]}\t{(o.get('generic_name') or [''])[0]}")
    return _cap(rows, "applications")


@mcp.tool()
def get_drug_application(application_number: str) -> str:
    """Get details of one Drugs@FDA application (sponsor, products, approval).

    Args:
        application_number: e.g. "NDA020702" or "ANDA207687".
    """
    j = _get("drugsfda.json", search=f'application_number:"{application_number}"', limit=1)
    res = j.get("results", [])
    if not res:
        return f"No application {application_number}."
    r = res[0]
    out = [f"application: {r.get('application_number')}", f"sponsor: {r.get('sponsor_name')}"]
    subs = r.get("submissions", []) or []
    approvals = [s.get("submission_status_date") for s in subs if s.get("submission_status") == "AP"]
    if approvals:
        out.append(f"first_approval: {min(approvals)}")
    out.append("products:")
    for p in (r.get("products") or [])[:15]:
        out.append(f"  - {p.get('brand_name','')} | {p.get('dosage_form','')} {p.get('route','')} "
                   f"| {p.get('marketing_status','')} | "
                   f"{'; '.join(a.get('name','')+' '+a.get('strength','') for a in p.get('active_ingredients',[]))}")
    return "\n".join(out)


@mcp.tool()
def count_drug_applications(field: str = "products.marketing_status", search: str = "") -> str:
    """Aggregate a count of Drugs@FDA applications grouped by a field.

    Args:
        field: openFDA field to group by (e.g. "products.marketing_status",
            "products.dosage_form.exact", "products.route.exact").
        search: optional openFDA search filter (e.g. 'openfda.generic_name:"aspirin"').
    """
    params = {"count": field, "limit": 25}
    if search.strip():
        params["search"] = search.strip()
    res = _get("drugsfda.json", **params).get("results", [])
    if not res:
        return f"No counts for field '{field}'."
    rows = [f"{field}\tcount"] + [f"{r.get('term')}\t{r.get('count')}" for r in res]
    return _cap(rows, "buckets")


@mcp.tool()
def get_drug_statistics(drug: str) -> str:
    """Approval/marketing statistics for a drug across Drugs@FDA (by status & dosage form).

    Args:
        drug: generic or brand name (e.g. "atorvastatin").
    """
    q = _name_query(drug)
    out = [f"drug: {drug}"]
    for label, field in [("by marketing status", "products.marketing_status"),
                         ("by dosage form", "products.dosage_form.exact"),
                         ("by route", "products.route.exact")]:
        res = _get("drugsfda.json", search=q, count=field, limit=10).get("results", [])
        if res:
            out.append(f"\n{label}:")
            out.extend(f"  {r.get('term')}: {r.get('count')}" for r in res[:10])
    return "\n".join(out) if len(out) > 1 else f"No statistics for '{drug}'."


@mcp.tool()
def list_pharmacologic_classes(drug: str = "") -> str:
    """List pharmacologic classes (EPC/MOA/PE/CS). For a drug, its classes; else top EPC classes.

    Args:
        drug: optional drug name; if empty, returns the most common EPC classes overall.
    """
    if drug.strip():
        j = _get("label.json", search=_name_query(drug), limit=1)
        res = j.get("results", [])
        if not res:
            return f"No label found for '{drug}'."
        o = res[0].get("openfda", {})
        out = [f"drug: {drug}"]
        for label, key in [("EPC (established class)", "pharm_class_epc"),
                           ("MOA (mechanism)", "pharm_class_moa"),
                           ("PE (physiologic effect)", "pharm_class_pe"),
                           ("CS (chemical structure)", "pharm_class_cs")]:
            vals = o.get(key)
            if vals:
                out.append(f"{label}: {', '.join(vals)}")
        return "\n".join(out) if len(out) > 1 else f"No pharmacologic classes on label for '{drug}'."
    res = _get("label.json", count="openfda.pharm_class_epc.exact", limit=25).get("results", [])
    rows = ["pharmacologic_class (EPC)\tlabel_count"] + [f"{r.get('term')}\t{r.get('count')}" for r in res]
    return _cap(rows, "classes")


@mcp.tool()
def get_generic_equivalents(drug: str, limit: int = 25) -> str:
    """Find generic (ANDA) and brand (NDA) equivalents sharing a drug's active ingredient.

    Args:
        drug: generic or brand name (e.g. "Lipitor", "atorvastatin").
        limit: max applications (default 25).
    """
    # Resolve the generic (active-ingredient) name first for a precise equivalence set.
    j = _get("drugsfda.json", search=_name_query(drug), limit=1)
    res = j.get("results", [])
    if not res:
        return f"No Drugs@FDA record for '{drug}'."
    generic = ((res[0].get("openfda", {}).get("generic_name") or [drug])[0])
    j = _get("drugsfda.json", search=f'openfda.generic_name:"{generic}"', limit=min(100, MAX_ROWS))
    rows = [f"# equivalents for {generic}", "application\ttype\tsponsor\tbrand"]
    for r in j.get("results", [])[:limit]:
        appn = r.get("application_number", "")
        typ = "generic" if appn.startswith("ANDA") else ("brand" if appn.startswith("NDA") else "other")
        brand = (r.get("openfda", {}).get("brand_name") or [""])[0]
        rows.append(f"{appn}\t{typ}\t{r.get('sponsor_name','')}\t{brand}")
    return _cap(rows, "applications") if len(rows) > 2 else f"No equivalents for '{drug}'."


@mcp.tool()
def search_drug_labels(query: str, limit: int = 5) -> str:
    """Search SPL drug labels; returns brand, indications snippet, and SPL id.

    Args:
        query: brand or generic name (e.g. "ibuprofen").
        limit: max labels (default 5).
    """
    j = _get("label.json", search=_name_query(query), limit=max(1, min(limit, 20)))
    res = j.get("results", [])
    if not res:
        return f"No drug labels for '{query}'."
    out = []
    for r in res:
        o = r.get("openfda", {})
        brand = (o.get("brand_name") or [""])[0]
        ind = (r.get("indications_and_usage") or [""])[0]
        ind = " ".join(ind.split())[:300]
        out.append(f"## {brand or (o.get('generic_name') or ['?'])[0]}  (spl_id: {(o.get('spl_id') or [''])[0]})\n{ind}")
    return "\n\n".join(out)


if __name__ == "__main__":
    mcp.run()
