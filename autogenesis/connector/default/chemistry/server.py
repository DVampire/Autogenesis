#!/usr/bin/env python3
"""Chemistry MCP server — small-molecule chemistry over PUBLIC APIs, no auth:

  * PubChem  (PUG REST)          — compound search, properties, similarity, bioassay, safety
  * ChEBI    (EBI OLS4)          — ontology search, entity details, is_a hierarchy
  * Rhea     (rhea-db.org REST)  — biochemical reaction search & lookup
  * BindingDB(bindingdb.org REST)— target binding affinities

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUGVIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
OLS = "https://www.ebi.ac.uk/ols4/api"
RHEA = "https://www.rhea-db.org/rhea"
BINDINGDB = "https://bindingdb.org/rest"
HDRS = {"User-Agent": "Autogenesis-chemistry/1.0", "Accept": "application/json"}
TIMEOUT = 60
MAX_ROWS = 60

mcp = FastMCP("chemistry")


def _get(url, **params):
    r = requests.get(url, params=params or None, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:200]}")
    return r


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ======================================================================= PubChem
@mcp.tool()
def pubchem_search_compounds(query: str, limit: int = 10) -> str:
    """Search PubChem compounds by name/synonym; returns CID, title, formula.

    Args:
        query: compound name (e.g. "caffeine", "aspirin").
        limit: max compounds (default 10).
    """
    j = _get(f"{PUG}/compound/name/{query}/cids/JSON").json()
    cids = j.get("IdentifierList", {}).get("CID", [])[:max(1, limit)]
    if not cids:
        return f"No PubChem compounds found for '{query}'."
    csv = ",".join(map(str, cids))
    props = _get(f"{PUG}/compound/cid/{csv}/property/Title,MolecularFormula,MolecularWeight/JSON"
                 ).json().get("PropertyTable", {}).get("Properties", [])
    rows = ["cid\ttitle\tformula\tMW"]
    for p in props:
        rows.append(f"{p.get('CID')}\t{p.get('Title','')}\t{p.get('MolecularFormula','')}\t{p.get('MolecularWeight','')}")
    return _cap(rows, "compounds")


@mcp.tool()
def pubchem_get_compounds(cids: list[int], properties: str = "") -> str:
    """Fetch properties for one or more PubChem CIDs.

    Args:
        cids: list of PubChem CIDs, e.g. [2519, 2244].
        properties: comma-separated PUG property names; default a useful set
            (MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey,IUPACName,XLogP).
    """
    if not cids:
        return "Error: `cids` must be non-empty."
    props = properties.strip() or "MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey,IUPACName,XLogP"
    csv = ",".join(str(c) for c in cids)
    data = _get(f"{PUG}/compound/cid/{csv}/property/{props}/JSON").json().get("PropertyTable", {}).get("Properties", [])
    if not data:
        return "No properties returned."
    keys = list(data[0].keys())
    rows = ["\t".join(keys)] + ["\t".join(str(p.get(k, "")) for k in keys) for p in data]
    return _cap(rows, "rows")


@mcp.tool()
def pubchem_similarity_search(smiles: str, threshold: int = 90, limit: int = 10) -> str:
    """2D-similarity search: find PubChem compounds similar to a SMILES.

    Args:
        smiles: query structure as SMILES.
        threshold: Tanimoto similarity threshold 0-100 (default 90).
        limit: max hits (default 10).
    """
    r = _get(f"{PUG}/compound/fastsimilarity_2d/smiles/{smiles}/cids/JSON",
             Threshold=threshold, MaxRecords=max(1, limit))
    cids = r.json().get("IdentifierList", {}).get("CID", [])
    if not cids:
        return "No similar compounds found."
    csv = ",".join(map(str, cids[:limit]))
    props = _get(f"{PUG}/compound/cid/{csv}/property/Title,MolecularFormula/JSON"
                 ).json().get("PropertyTable", {}).get("Properties", [])
    rows = ["cid\ttitle\tformula"] + [f"{p.get('CID')}\t{p.get('Title','')}\t{p.get('MolecularFormula','')}" for p in props]
    return _cap(rows, "hits")


@mcp.tool()
def pubchem_get_bioassay_summary(cid: int) -> str:
    """Summarize a compound's PubChem bioassay activity (active/inactive counts + samples).

    Args:
        cid: PubChem compound CID.
    """
    tbl = _get(f"{PUG}/compound/cid/{cid}/assaysummary/JSON").json().get("Table", {})
    cols = [c for c in tbl.get("Columns", {}).get("Column", [])]
    rows_raw = tbl.get("Row", [])
    if not rows_raw:
        return f"No bioassay data for CID {cid}."
    idx = {c: i for i, c in enumerate(cols)}
    oc = idx.get("Activity Outcome")
    tgt = idx.get("Target Name")
    aid = idx.get("AID")
    counts: dict = {}
    actives = []
    for row in rows_raw:
        cells = row.get("Cell", [])
        outcome = cells[oc] if oc is not None and oc < len(cells) else ""
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == "Active" and len(actives) < 15:
            actives.append(f"AID {cells[aid] if aid is not None else '?'}\t{cells[tgt] if tgt is not None and tgt<len(cells) else ''}")
    summary = [f"CID {cid} — {len(rows_raw)} bioassay records",
               "outcomes: " + ", ".join(f"{k or 'Unspecified'}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))]
    if actives:
        summary.append("\nsample active assays (AID<TAB>target):")
        summary.extend(actives)
    return "\n".join(summary)


def _find_section(node, heading):
    for sec in node.get("Section", []) or []:
        if sec.get("TOCHeading") == heading:
            return sec
        found = _find_section(sec, heading)
        if found:
            return found
    return None


@mcp.tool()
def pubchem_get_safety(cid: int) -> str:
    """Get GHS safety classification (signal, hazard statements, pictograms) for a compound.

    Args:
        cid: PubChem compound CID.
    """
    rec = _get(f"{PUGVIEW}/data/compound/{cid}/JSON", heading="GHS Classification").json().get("Record", {})
    sec = _find_section(rec, "GHS Classification")
    if not sec:
        return f"No GHS classification available for CID {cid}."
    out = [f"CID {cid} — GHS Classification"]
    for info in sec.get("Information", []) or []:
        name = info.get("Name", "")
        val = info.get("Value", {})
        strings = [s.get("String", "") for s in val.get("StringWithMarkup", []) or []]
        if strings:
            out.append(f"{name}: " + "; ".join(strings[:8]))
    return _cap(out, "lines")


# ========================================================================= ChEBI
@mcp.tool()
def chebi_search(query: str, limit: int = 10) -> str:
    """Search ChEBI (via EBI OLS) for chemical entities by name.

    Args:
        query: chemical name (e.g. "caffeine").
        limit: max results (default 10).
    """
    docs = _get(f"{OLS}/search", q=query, ontology="chebi", rows=max(1, limit)
                ).json().get("response", {}).get("docs", [])
    rows = ["chebi_id\tlabel"] + [f"{d.get('obo_id','')}\t{d.get('label','')}" for d in docs]
    return "\n".join(rows) if len(rows) > 1 else f"No ChEBI entities for '{query}'."


def _chebi_term(chebi_id: str) -> dict:
    cid = "CHEBI:" + chebi_id.split(":")[-1]
    terms = _get(f"{OLS}/ontologies/chebi/terms", obo_id=cid).json().get("_embedded", {}).get("terms", [])
    if not terms:
        raise RuntimeError(f"ChEBI entity '{cid}' not found.")
    return terms[0]


@mcp.tool()
def chebi_get_entity(chebi_id: str) -> str:
    """Get a ChEBI entity's definition and chemical properties.

    Args:
        chebi_id: e.g. "CHEBI:27732" (or "27732").
    """
    t = _chebi_term(chebi_id)
    ann = t.get("annotation", {}) or {}
    def a(k):
        v = ann.get(k)
        return v[0] if isinstance(v, list) and v else (v or "")
    out = [f"id: {t.get('obo_id','')}", f"name: {t.get('label','')}"]
    desc = t.get("description") or []
    if desc:
        out.append("definition: " + (desc[0] if isinstance(desc, list) else str(desc)))
    for label, key in [("formula", "generalized_empirical_formula"), ("mass", "mass"),
                       ("charge", "charge"), ("smiles", "smiles_string"),
                       ("inchikey", "inchi_key_string")]:
        if a(key):
            out.append(f"{label}: {a(key)}")
    return "\n".join(out)


@mcp.tool()
def chebi_get_ontology(chebi_id: str) -> str:
    """Get a ChEBI entity's is_a hierarchy (parents and children).

    Args:
        chebi_id: e.g. "CHEBI:27732".
    """
    t = _chebi_term(chebi_id)
    links = t.get("_links", {})
    out = [f"{t.get('obo_id','')} — {t.get('label','')}"]
    for rel in ("parents", "children"):
        href = (links.get(rel) or {}).get("href")
        if not href:
            continue
        terms = _get(href).json().get("_embedded", {}).get("terms", [])
        out.append(f"\n{rel}:")
        out.extend(f"- {x.get('obo_id','')}\t{x.get('label','')}" for x in terms[:MAX_ROWS])
    return "\n".join(out)


# ========================================================================== Rhea
@mcp.tool()
def rhea_search_reactions(query: str, limit: int = 10) -> str:
    """Search Rhea biochemical reactions by keyword/compound.

    Args:
        query: e.g. "caffeine", "ATP", a ChEBI name.
        limit: max reactions (default 10).
    """
    res = _get(RHEA, query=query, columns="rhea-id,equation", format="json",
               limit=max(1, limit)).json().get("results", [])
    rows = ["rhea_id\tequation"] + [f"RHEA:{r.get('id','')}\t{r.get('equation','')}" for r in res]
    return "\n".join(rows) if len(rows) > 1 else f"No Rhea reactions for '{query}'."


@mcp.tool()
def rhea_get_reaction(rhea_id: str) -> str:
    """Get a Rhea reaction's equation, participating ChEBI ids, and EC number.

    Args:
        rhea_id: e.g. "RHEA:10280" or "10280".
    """
    rid = "RHEA:" + str(rhea_id).split(":")[-1]
    res = _get(RHEA, query=rid, columns="rhea-id,equation", format="json").json().get("results", [])
    if not res:
        return f"Reaction {rid} not found."
    r = res[0]
    chebis = ", ".join(sorted(set(re.findall(r'data-molid="(chebi:\d+)"', r.get("htmlequation", ""), re.I))))
    out = [f"id: RHEA:{r.get('id','')}", f"equation: {r.get('equation','')}",
           f"status: {r.get('status','')}", f"balanced: {r.get('balanced','')}"]
    if chebis:
        out.append(f"chebi participants: {chebis}")
    return "\n".join(out)


# ====================================================================== BindingDB
def _bdb_find_list(obj):
    """Defensively locate the list of affinity records in a BindingDB JSON response."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            got = _bdb_find_list(v)
            if got:
                return got
    return None


def _bdb_num(x):
    try:
        return float(str(x).lstrip("<>=~"))
    except Exception:
        return float("inf")


def _bdb_field(d: dict, *names):
    """Read a field that BindingDB may return bare or prefixed with 'bdb.'."""
    for n in names:
        for key in (n, f"bdb.{n}"):
            if d.get(key) not in (None, ""):
                return d[key]
    return ""


@mcp.tool()
def bindingdb_ligands_by_target(uniprot: str, cutoff_nm: int = 100, limit: int = 40, out_file: str = "") -> str:
    """Get measured ligand binding affinities for a protein target from BindingDB.

    Args:
        uniprot: UniProt accession of the target (e.g. "P00533" for EGFR).
        cutoff_nm: only return ligands with affinity <= this many nM (default 100 = potent).
        limit: max ligands (default 40).
    Returns ligands sorted by affinity (most potent first).
    """
    r = _get(f"{BINDINGDB}/getLigandsByUniprots", uniprot=uniprot, cutoff=cutoff_nm,
             code="0", response="application/json")
    try:
        data = r.json()
    except Exception:
        return f"BindingDB returned no parseable data for {uniprot}."
    recs = _bdb_find_list(data) or []
    if not recs:
        return f"No BindingDB affinities for {uniprot} within {cutoff_nm} nM."
    recs.sort(key=lambda d: _bdb_num(_bdb_field(d, "affinity")))
    header = "monomerId\taffinity_type\taffinity(nM)\tsmiles"
    if out_file:
        import os
        full = [header]
        for d in recs[:max(1, limit)]:
            mid = _bdb_field(d, "monomerid", "monomerId")
            smi = _bdb_field(d, "smile", "smiles")
            full.append(f"{mid}\t{_bdb_field(d,'affinity_type')}\t{_bdb_field(d,'affinity')}\t{smi}")
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w") as fh:
            fh.write("\n".join(full))
        return f"Wrote {len(full)-1} ligand rows for {uniprot} (<= {cutoff_nm} nM) to {out_file}"
    rows = [f"# BindingDB ligands for {uniprot} (<= {cutoff_nm} nM)", header]
    for d in recs[:max(1, limit)]:
        mid = _bdb_field(d, "monomerid", "monomerId")
        smi = _bdb_field(d, "smile", "smiles")
        rows.append(f"{mid}\t{_bdb_field(d,'affinity_type')}\t{_bdb_field(d,'affinity')}\t{smi}")
    return _cap(rows, "ligands")


@mcp.tool()
def bindingdb_targets_by_compound(smiles: str, similarity_cutoff: float = 0.85, limit: int = 40) -> str:
    """Find protein targets bound by compounds structurally similar to a query molecule.

    Uses BindingDB's getTargetByCompound: does a 2D similarity search for the query
    SMILES and returns the targets its similar compounds bind, with measured affinities.

    Args:
        smiles: query molecule SMILES (e.g. "CC(=O)OC1=CC=CC=C1C(=O)O" for aspirin).
        similarity_cutoff: Tanimoto similarity threshold, 0-1 (default 0.85).
        limit: max target-affinity rows (default 40).
    """
    r = _get(f"{BINDINGDB}/getTargetByCompound", smiles=smiles,
             cutoff=str(similarity_cutoff), response="application/json")
    try:
        data = r.json()
    except Exception:
        return f"BindingDB returned no parseable data for SMILES '{smiles}'."
    recs = _bdb_find_list(data) or []
    if not recs:
        return f"No BindingDB targets for compounds similar to '{smiles}' (Tanimoto >= {similarity_cutoff})."
    recs.sort(key=lambda d: _bdb_num(_bdb_field(d, "affinity")))
    rows = [f"# BindingDB targets for compounds similar to query (Tanimoto >= {similarity_cutoff})",
            "target\tspecies\taffinity_type\taffinity(nM)\tsmiles"]
    for d in recs[:max(1, limit)]:
        smi = _bdb_field(d, "smiles", "smile")
        rows.append(f"{_bdb_field(d,'target')}\t{_bdb_field(d,'species')}\t"
                    f"{_bdb_field(d,'affinity_type')}\t{_bdb_field(d,'affinity')}\t{smi[:50]}")
    return _cap(rows, "targets")


if __name__ == "__main__":
    mcp.run()
