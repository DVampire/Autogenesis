#!/usr/bin/env python3
"""Structures & Interactions MCP server — macromolecular structures and molecular
interactions over PUBLIC APIs, no auth:

  * RCSB PDB   (data.rcsb.org / search.rcsb.org) — experimental 3D structures
  * AlphaFold  (alphafold.ebi.ac.uk)             — predicted structures
  * EMDB       (ebi.ac.uk/emdb)                   — cryo-EM maps
  * Complex Portal (ebi.ac.uk/intact/complex-ws) — curated protein complexes
  * IntAct     (ebi.ac.uk/intact/ws)             — molecular interaction networks

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import requests
from mcp.server.fastmcp import FastMCP

PDB_DATA = "https://data.rcsb.org/rest/v1/core"
PDB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
ALPHAFOLD = "https://alphafold.ebi.ac.uk/api"
EMDB = "https://www.ebi.ac.uk/emdb/api"
COMPLEXPORTAL = "https://www.ebi.ac.uk/intact/complex-ws"
INTACT = "https://www.ebi.ac.uk/intact/ws"
HDRS = {"User-Agent": "Autogenesis-struct/1.0", "Accept": "application/json"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("structures_interactions")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:100]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ==================================================================== RCSB PDB
@mcp.tool()
def pdb_search_structures(query: str, limit: int = 15) -> str:
    """Search RCSB PDB for experimental 3D structures by full-text query.

    Args:
        query: search text (e.g. "hemoglobin", "SARS-CoV-2 spike").
        limit: max structures (default 15).
    """
    body = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
            "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": max(1, min(limit, MAX_ROWS))}}}
    r = requests.post(PDB_SEARCH, json=body, headers=HDRS, timeout=TIMEOUT)
    if r.status_code == 204:
        return f"No PDB structures for '{query}'."
    r.raise_for_status()
    j = r.json()
    ids = [x.get("identifier") for x in j.get("result_set", [])]
    if not ids:
        return f"No PDB structures for '{query}'."
    return f"# {j.get('total_count','?')} structures match; showing {len(ids)}\n" + ", ".join(ids)


@mcp.tool()
def pdb_get_structures(pdb_id: str) -> str:
    """Get an RCSB PDB structure's metadata (title, method, resolution, organism).

    Args:
        pdb_id: 4-character PDB id (e.g. "4HHB").
    """
    e = _get(f"{PDB_DATA}/entry/{pdb_id}")
    info = e.get("rcsb_entry_info", {})
    res = info.get("resolution_combined")
    method = (e.get("exptl") or [{}])[0].get("method", "")
    return (f"pdb_id: {pdb_id.upper()}\ntitle: {e.get('struct',{}).get('title','')}\nmethod: {method}\n"
            f"resolution: {res[0] if isinstance(res,list) and res else ''} Å\n"
            f"keywords: {e.get('struct_keywords',{}).get('pdbx_keywords','')}\n"
            f"polymer_entities: {info.get('polymer_entity_count','')}\ndeposited: {e.get('rcsb_accession_info',{}).get('initial_release_date','')[:10]}")


@mcp.tool()
def pdb_get_entities(pdb_id: str) -> str:
    """List the polymer entities (chains) of a PDB structure.

    Args:
        pdb_id: PDB id (e.g. "4HHB").
    """
    cid = _get(f"{PDB_DATA}/entry/{pdb_id}").get("rcsb_entry_container_identifiers", {})
    rows = ["entity\tdescription\ttype\torganism"]
    for eid in (cid.get("polymer_entity_ids") or [])[:MAX_ROWS]:
        pe = _get(f"{PDB_DATA}/polymer_entity/{pdb_id}/{eid}")
        desc = pe.get("rcsb_polymer_entity", {}).get("pdbx_description", "")
        typ = pe.get("entity_poly", {}).get("rcsb_entity_polymer_type", "")
        org = (pe.get("rcsb_entity_source_organism") or [{}])[0].get("scientific_name", "")
        rows.append(f"{eid}\t{(desc or '')[:45]}\t{typ}\t{org}")
    return "\n".join(rows) if len(rows) > 1 else f"No polymer entities for {pdb_id}."


@mcp.tool()
def pdb_get_ligands(pdb_id: str) -> str:
    """List the ligands (non-polymer entities) of a PDB structure.

    Args:
        pdb_id: PDB id (e.g. "4HHB").
    """
    cid = _get(f"{PDB_DATA}/entry/{pdb_id}").get("rcsb_entry_container_identifiers", {})
    ids = cid.get("non_polymer_entity_ids") or []
    if not ids:
        return f"No ligands (non-polymer entities) in {pdb_id}."
    rows = ["comp_id\tname"]
    for eid in ids[:MAX_ROWS]:
        ne = _get(f"{PDB_DATA}/nonpolymer_entity/{pdb_id}/{eid}")
        np = ne.get("pdbx_entity_nonpoly", {})
        rows.append(f"{np.get('comp_id','')}\t{np.get('name','')}")
    return "\n".join(rows)


# ================================================================== AlphaFold
@mcp.tool()
def alphafold_get_prediction(uniprot: str) -> str:
    """Get the AlphaFold predicted structure for a UniProt accession.

    Args:
        uniprot: UniProt accession (e.g. "P04637").
    """
    data = _get(f"{ALPHAFOLD}/prediction/{uniprot}")
    if not data:
        return f"No AlphaFold prediction for {uniprot}."
    a = data[0]
    return (f"uniprot: {a.get('uniprotAccession','')}\ngene: {a.get('gene','')}\n"
            f"organism: {a.get('organismScientificName','')}\n"
            f"coverage: {a.get('uniprotStart','')}-{a.get('uniprotEnd','')} of {a.get('uniprotEnd','')}\n"
            f"mean_pLDDT: {a.get('globalMetricValue','')}\ncreated: {a.get('modelCreatedDate','')}\n"
            f"pdb: {a.get('pdbUrl','')}\ncif: {a.get('cifUrl','')}")


@mcp.tool()
def alphafold_check_coverage(uniprot: str) -> str:
    """Check whether AlphaFold has a prediction for a UniProt accession and its coverage.

    Args:
        uniprot: UniProt accession (e.g. "P04637").
    """
    try:
        data = _get(f"{ALPHAFOLD}/prediction/{uniprot}")
    except RuntimeError:
        return f"No AlphaFold prediction available for {uniprot}."
    if not data:
        return f"No AlphaFold prediction available for {uniprot}."
    a = data[0]
    length = len(a.get("uniprotSequence", "") or "")
    return (f"uniprot: {uniprot}\nhas_prediction: yes\ncovered_residues: {a.get('uniprotStart','')}-{a.get('uniprotEnd','')}\n"
            f"sequence_length: {length}\nmean_pLDDT: {a.get('globalMetricValue','')}")


# ======================================================================= EMDB
@mcp.tool()
def emdb_search_entries(query: str, limit: int = 15) -> str:
    """Search EMDB cryo-EM entries by keyword.

    Args:
        query: search text (e.g. "ribosome", "spike").
        limit: max entries (default 15).
    """
    data = _get(f"{EMDB}/search/{query}", rows=max(1, min(limit, MAX_ROWS)))
    entries = data if isinstance(data, list) else data.get("results", data.get("hits", []))
    if not entries:
        return f"No EMDB entries for '{query}'."
    rows = ["emdb_id\ttitle"]
    for e in entries[:limit]:
        eid = e.get("emdb_id") or e.get("id") or e.get("emd_id", "")
        title = e.get("title") or (e.get("admin") or {}).get("title", "") if isinstance(e, dict) else ""
        rows.append(f"{eid}\t{(title or '')[:70]}")
    return _cap(rows, "entries")


def _emdb_entry(emdb_id: str) -> dict:
    return _get(f"{EMDB}/entry/{emdb_id}")


@mcp.tool()
def emdb_get_entries(emdb_id: str) -> str:
    """Get an EMDB cryo-EM entry's summary (title, method, resolution).

    Args:
        emdb_id: EMDB id (e.g. "EMD-3489").
    """
    e = _emdb_entry(emdb_id)
    title = (e.get("admin") or {}).get("title", "")
    # resolution is nested under structure_determination -> image_processing -> final_reconstruction
    res = ""
    sd = e.get("structure_determination_list", {})
    dets = sd.get("structure_determination", []) if isinstance(sd, dict) else []
    for d in dets:
        method = d.get("method", "")
        for ip in d.get("image_processing", []) or []:
            fr = ip.get("final_reconstruction", {})
            r = fr.get("resolution", {})
            if isinstance(r, dict) and r.get("valueOf_"):
                res = f"{r.get('valueOf_')} {r.get('units','')}"
        if method:
            return f"emdb_id: {emdb_id}\ntitle: {title}\nmethod: {method}\nresolution: {res}"
    return f"emdb_id: {emdb_id}\ntitle: {title}\nresolution: {res}"


@mcp.tool()
def emdb_get_entry_section(emdb_id: str, section: str = "sample") -> str:
    """Get one section of an EMDB entry's record as JSON-ish text.

    Args:
        emdb_id: EMDB id (e.g. "EMD-3489").
        section: one of admin / sample / map / interpretation /
            structure_determination_list / crossreferences.
    """
    e = _emdb_entry(emdb_id)
    if section not in e:
        return f"Section '{section}' not found. Available: {', '.join(k for k in e if not k.startswith('_'))}"
    import json as _j
    return f"# {emdb_id} — {section}\n" + _j.dumps(e[section], ensure_ascii=False, indent=1)[:3000]


@mcp.tool()
def emdb_get_validation(emdb_id: str) -> str:
    """Get validation-relevant info for an EMDB entry (resolution & processing).

    NOTE: EMDB serves full validation reports as PDFs; this summarizes the processing
    and resolution from the entry record.

    Args:
        emdb_id: EMDB id (e.g. "EMD-3489").
    """
    summary = emdb_get_entries(emdb_id)
    return (summary + f"\nfull_validation_report: https://www.ebi.ac.uk/emdb/{emdb_id} "
            f"(EMDB serves validation reports as downloadable PDFs).")


# ============================================================== Complex Portal
def _cp_search(query: str, limit: int):
    return _get(f"{COMPLEXPORTAL}/search/{query}", size=max(1, min(limit, MAX_ROWS))).get("elements", [])


@mcp.tool()
def complexportal_get_complexes(query: str, limit: int = 15) -> str:
    """Get curated protein complexes from Complex Portal by name or complex accession.

    Args:
        query: complex name/keyword or accession (e.g. "GBAF" or "CPX-4084").
        limit: max complexes (default 15).
    """
    els = _cp_search(query, limit)
    if query.upper().startswith("CPX-"):
        els = [e for e in els if e.get("complexAC", "").upper() == query.upper()] or els
    if not els:
        return f"No Complex Portal complexes for '{query}'."
    rows = ["complexAC\tname\tspecies"]
    for e in els[:limit]:
        rows.append(f"{e.get('complexAC','')}\t{(e.get('complexName') or '')[:55]}\t{e.get('organismName','')}")
    return _cap(rows, "complexes")


@mcp.tool()
def complexportal_search_by_participant(participant: str, limit: int = 15) -> str:
    """Find protein complexes containing a given participant (protein/gene).

    Args:
        participant: protein name, gene, or UniProt accession (e.g. "CTCF", "P49711").
        limit: max complexes (default 15).
    """
    els = _cp_search(participant, limit)
    if not els:
        return f"No complexes with participant '{participant}'."
    rows = [f"# complexes involving {participant}", "complexAC\tname\tspecies"]
    for e in els[:limit]:
        rows.append(f"{e.get('complexAC','')}\t{(e.get('complexName') or '')[:55]}\t{e.get('organismName','')}")
    return _cap(rows, "complexes")


# ===================================================================== IntAct
def _intact_interactions(query: str, limit: int):
    j = _get(f"{INTACT}/interaction/findInteractions/{query}", page=0, pageSize=max(1, min(limit, MAX_ROWS)))
    return j.get("content", []) if isinstance(j, dict) else []


@mcp.tool()
def intact_fetch_interactions(query: str, limit: int = 20) -> str:
    """Fetch molecular interactions for a molecule from IntAct.

    Args:
        query: gene/protein name or accession (e.g. "TP53").
        limit: max interactions (default 20).
    """
    items = _intact_interactions(query, limit)
    if not items:
        return f"No IntAct interactions for '{query}'."
    rows = ["moleculeA\tmoleculeB\ttaxA\ttaxB\tdetection\ttype"]
    for it in items:
        rows.append(f"{it.get('moleculeA','')}\t{it.get('moleculeB','')}\t{it.get('taxIdA','')}\t"
                    f"{it.get('taxIdB','')}\t{(it.get('detectionMethod') or '')[:22]}\t{(it.get('type') or '')[:20]}")
    return _cap(rows, "interactions")


@mcp.tool()
def intact_get_interactor(query: str) -> str:
    """Get interactor (molecule) info from IntAct.

    Args:
        query: gene/protein name or accession (e.g. "TP53").
    """
    j = _get(f"{INTACT}/interactor/findInteractor/{query}", page=0, pageSize=5)
    items = j.get("content", []) if isinstance(j, dict) else (j if isinstance(j, list) else [])
    if not items:
        return f"No IntAct interactor for '{query}'."
    rows = ["ac\tname\ttype\tspecies\tinteractionCount"]
    for it in items[:MAX_ROWS]:
        rows.append(f"{it.get('interactorAc', it.get('ac',''))}\t{it.get('interactorName', it.get('name',''))}\t"
                    f"{it.get('interactorType','')}\t{it.get('interactorSpecies','')}\t{it.get('interactionCount','')}")
    return _cap(rows, "interactors")


@mcp.tool()
def intact_get_interaction_details(query: str, limit: int = 10) -> str:
    """Get detailed evidence for interactions of a molecule (method, type, publication).

    Args:
        query: gene/protein name or accession (e.g. "TP53").
        limit: max interactions (default 10).
    """
    items = _intact_interactions(query, limit)
    if not items:
        return f"No IntAct interactions for '{query}'."
    out = []
    for it in items:
        out.append(f"## {it.get('moleculeA','')} — {it.get('moleculeB','')}\n"
                   f"detection: {it.get('detectionMethod','')}\ntype: {it.get('type','')}\n"
                   f"confidence: {it.get('confidenceValues') or it.get('miscore','')}\n"
                   f"publication: {it.get('publicationIdentifiers') or it.get('publicationPubmedIdentifier','')}")
    return "\n\n".join(out)


@mcp.tool()
def intact_build_network(query: str, limit: int = 30) -> str:
    """Build an interaction network (nodes + edges) around a molecule from IntAct.

    Args:
        query: gene/protein name or accession (e.g. "TP53").
        limit: max interactions to include (default 30).
    """
    items = _intact_interactions(query, limit)
    if not items:
        return f"No IntAct interactions for '{query}'."
    nodes, edges = set(), []
    for it in items:
        a, b = it.get("moleculeA", ""), it.get("moleculeB", "")
        if a:
            nodes.add(a)
        if b:
            nodes.add(b)
        if a and b:
            edges.append(f"{a} -- {b}")
    out = [f"# network for {query}: {len(nodes)} nodes, {len(edges)} edges", "nodes: " + ", ".join(sorted(nodes)[:40]), "", "edges:"]
    out += edges[:MAX_ROWS]
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
