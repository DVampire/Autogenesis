#!/usr/bin/env python3
"""Omics Archives MCP server — omics data repositories over PUBLIC APIs, no auth:

  * ArrayExpress / BioStudies (EBI) — functional-genomics experiments
  * GEO (NCBI E-utilities)          — Gene Expression Omnibus series
  * MGnify (EBI)                    — metagenomics studies & analyses
  * PRIDE (EBI)                     — proteomics projects
  * MetaboLights (EBI)             — metabolomics studies & data files

GEO endpoint mappings referenced from open-source MCPmed/GEOmcp (NCBI E-utils).
Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

BIOSTUDIES = "https://www.ebi.ac.uk/biostudies/api/v1"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MGNIFY = "https://www.ebi.ac.uk/metagenomics/api/v1"
PRIDE = "https://www.ebi.ac.uk/pride/ws/archive/v2"
METABOLIGHTS = "https://www.ebi.ac.uk/metabolights/ws"
HDRS = {"User-Agent": "Autogenesis-omics/1.0", "Accept": "application/json"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("omics_archives")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _attrs(obj) -> dict:
    return {a.get("name", ""): a.get("value", "") for a in (obj.get("attributes") or []) if isinstance(a, dict)}


def _names(lst) -> str:
    """Join a list of names whose items may be dicts ({name:..}) or plain strings."""
    return ", ".join((o.get("name", "") if isinstance(o, dict) else str(o)) for o in (lst or []))


# ==================================================== ArrayExpress / BioStudies
@mcp.tool()
def arrayexpress_search_experiments(query: str, limit: int = 15) -> str:
    """Search ArrayExpress (BioStudies) functional-genomics experiments.

    Args:
        query: search text (e.g. "breast cancer RNA-seq").
        limit: max experiments (default 15).
    """
    j = _get(f"{BIOSTUDIES}/search", query=query, collection="arrayexpress", pageSize=max(1, min(limit, MAX_ROWS)))
    hits = j.get("hits", [])
    if not hits:
        return f"No ArrayExpress experiments for '{query}'."
    rows = [f"# {j.get('totalHits','?')} experiments match; showing {len(hits)}", "accession\ttitle\trelease"]
    for h in hits:
        rows.append(f"{h.get('accession','')}\t{(h.get('title') or '')[:70]}\t{h.get('release_date', h.get('release',''))}")
    return _cap(rows, "experiments")


@mcp.tool()
def arrayexpress_get_experiment(accession: str) -> str:
    """Get an ArrayExpress experiment's metadata.

    Args:
        accession: experiment accession (e.g. "E-GEOD-17155").
    """
    s = _get(f"{BIOSTUDIES}/studies/{accession}")
    a = _attrs(s.get("section", {})) | _attrs(s)
    out = [f"accession: {s.get('accno', accession)}"]
    for k in ("Title", "Description", "Organism", "Study type", "Experiment type"):
        if a.get(k):
            out.append(f"{k}: {a[k][:400]}")
    return "\n".join(out) if len(out) > 1 else f"Experiment {accession} (no descriptive attributes found)."


def _collect_files(node, out):
    if isinstance(node, dict):
        if "path" in node:
            out.append(node)
        for v in node.values():
            _collect_files(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_files(v, out)


@mcp.tool()
def arrayexpress_get_experiment_files(accession: str, limit: int = 25) -> str:
    """List the data files of an ArrayExpress experiment.

    Args:
        accession: experiment accession (e.g. "E-GEOD-17155").
        limit: max files (default 25).
    """
    s = _get(f"{BIOSTUDIES}/studies/{accession}")
    files = []
    _collect_files(s.get("section", {}), files)
    if not files:
        return f"No files listed for {accession}."
    rows = [f"# {len(files)} files in {accession}", "path\tsize\ttype"]
    seen = set()
    for f in files:
        p = f.get("path", "")
        if p in seen:
            continue
        seen.add(p)
        fa = _attrs(f)
        rows.append(f"{p}\t{f.get('size','')}\t{fa.get('Type', fa.get('type',''))}")
        if len(rows) > limit + 1:
            break
    return _cap(rows, "files")


@mcp.tool()
def arrayexpress_get_experiment_samples(accession: str) -> str:
    """Summarize the samples/assays of an ArrayExpress experiment (from its SDRF).

    Args:
        accession: experiment accession (e.g. "E-GEOD-17155").
    """
    s = _get(f"{BIOSTUDIES}/studies/{accession}")
    files = []
    _collect_files(s.get("section", {}), files)
    sdrf = [f.get("path", "") for f in files if "sdrf" in f.get("path", "").lower()]
    a = _attrs(s.get("section", {}))
    lines = [f"accession: {accession}"]
    if a.get("Organism"):
        lines.append(f"organism: {a['Organism']}")
    if sdrf:
        lines.append("sample/assay table (SDRF) files: " + ", ".join(sdrf))
        lines.append(f"Download an SDRF for the full sample sheet, e.g.: "
                     f"https://www.ebi.ac.uk/biostudies/files/{accession}/{sdrf[0]}")
    else:
        lines.append("No SDRF sample sheet found in the study files.")
    return "\n".join(lines)


# ============================================================================ GEO
@mcp.tool()
def geo_search_series(query: str, limit: int = 15) -> str:
    """Search NCBI GEO for expression series (GSE) by keyword.

    Args:
        query: search text (e.g. "breast cancer").
        limit: max series (default 15).
    """
    es = _get(f"{EUTILS}/esearch.fcgi", db="gds", term=f"({query}) AND gse[ETYP]",
              retmax=max(1, min(limit, MAX_ROWS)), retmode="json")
    ids = es.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return f"No GEO series for '{query}'."
    summ = _get(f"{EUTILS}/esummary.fcgi", db="gds", id=",".join(ids), retmode="json").get("result", {})
    rows = ["accession\tn_samples\ttype\ttitle"]
    for uid in summ.get("uids", []):
        d = summ.get(uid, {})
        rows.append(f"GSE{d.get('accession','').replace('GSE','')}\t{d.get('n_samples','')}\t"
                    f"{(d.get('gdstype') or '')[:30]}\t{(d.get('title') or '')[:60]}")
    return _cap(rows, "series")


@mcp.tool()
def geo_get_series(gse: str) -> str:
    """Get details of a GEO series by accession (GSE id).

    Args:
        gse: series accession (e.g. "GSE17155").
    """
    es = _get(f"{EUTILS}/esearch.fcgi", db="gds", term=f"{gse}[ACCN] AND gse[ETYP]", retmode="json")
    ids = es.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return f"No GEO series {gse}."
    d = _get(f"{EUTILS}/esummary.fcgi", db="gds", id=ids[0], retmode="json").get("result", {}).get(ids[0], {})
    return (f"accession: GSE{d.get('accession','').replace('GSE','')}\ntitle: {d.get('title','')}\n"
            f"type: {d.get('gdstype','')}\nsamples: {d.get('n_samples','')}\ntaxon: {d.get('taxon','')}\n"
            f"platform: GPL{d.get('gpl','')}\npubmed: {', '.join(map(str, d.get('pubmedids', [])))}\n"
            f"summary: {(d.get('summary') or '')[:500]}")


# ========================================================================= MGnify
@mcp.tool()
def mgnify_search_studies(query: str, limit: int = 15) -> str:
    """Search MGnify metagenomics studies.

    Args:
        query: search text (e.g. "human gut microbiome").
        limit: max studies (default 15).
    """
    j = _get(f"{MGNIFY}/studies", search=query, page_size=max(1, min(limit, MAX_ROWS)))
    data = j.get("data", [])
    if not data:
        return f"No MGnify studies for '{query}'."
    rows = ["accession\tstudy_name\tbiome"]
    for d in data:
        at = d.get("attributes", {})
        biome = (((d.get("relationships") or {}).get("biomes") or {}).get("data") or [{}])
        rows.append(f"{d.get('id','')}\t{(at.get('study-name') or '')[:55]}\t{at.get('centre-name','')}")
    return _cap(rows, "studies")


@mcp.tool()
def mgnify_get_studies(study_id: str) -> str:
    """Get an MGnify study's metadata.

    Args:
        study_id: MGnify study accession (e.g. "MGYS00006862").
    """
    at = _get(f"{MGNIFY}/studies/{study_id}").get("data", {}).get("attributes", {})
    return (f"accession: {study_id}\nname: {at.get('study-name','')}\n"
            f"centre: {at.get('centre-name','')}\nsamples: {at.get('samples-count','')}\n"
            f"abstract: {(at.get('study-abstract') or '')[:500]}")


@mcp.tool()
def mgnify_get_study_analyses(study_id: str, limit: int = 20) -> str:
    """List the analyses of an MGnify study.

    Args:
        study_id: MGnify study accession (e.g. "MGYS00006862").
        limit: max analyses (default 20).
    """
    j = _get(f"{MGNIFY}/studies/{study_id}/analyses", page_size=max(1, min(limit, MAX_ROWS)))
    data = j.get("data", [])
    if not data:
        return f"No analyses for {study_id}."
    rows = ["analysis_id\texperiment_type\tpipeline"]
    for a in data:
        at = a.get("attributes", {})
        rows.append(f"{a.get('id','')}\t{at.get('experiment-type','')}\t{at.get('pipeline-version','')}")
    return _cap(rows, "analyses")


# ========================================================================== PRIDE
@mcp.tool()
def pride_search_projects(keyword: str, limit: int = 15) -> str:
    """Search PRIDE proteomics projects by keyword.

    Args:
        keyword: search text (e.g. "melanoma phosphoproteome").
        limit: max projects (default 15).
    """
    data = _get(f"{PRIDE}/search/projects", keyword=keyword, pageSize=max(1, min(limit, MAX_ROWS)))
    projs = data if isinstance(data, list) else data.get("_embedded", {}).get("projects", [])
    if not projs:
        return f"No PRIDE projects for '{keyword}'."
    rows = ["accession\ttitle\torganisms"]
    for p in projs:
        orgs = _names(p.get("organisms"))
        rows.append(f"{p.get('accession','')}\t{(p.get('title') or '')[:60]}\t{orgs}")
    return _cap(rows, "projects")


@mcp.tool()
def pride_get_projects(accession: str) -> str:
    """Get a PRIDE project's metadata.

    Args:
        accession: PRIDE project accession (e.g. "PXD079445").
    """
    p = _get(f"{PRIDE}/projects/{accession}")
    orgs = _names(p.get("organisms"))
    insts = ", ".join(str(i) for i in (p.get("instruments") or []) if i)
    return (f"accession: {p.get('accession','')}\ntitle: {p.get('title','')}\norganisms: {orgs}\n"
            f"instruments: {insts}\ndescription: {(p.get('projectDescription') or '')[:500]}")


@mcp.tool()
def pride_search_project_proteins(accession: str) -> str:
    """Proteins reported in a PRIDE project.

    NOTE: PRIDE exposes no simple public per-project protein-list API; this returns
    pointers to the project's protein data instead.

    Args:
        accession: PRIDE project accession (e.g. "PXD079445").
    """
    return (f"accession: {accession}\nPRIDE has no public per-project protein-list endpoint. "
            f"Browse identified proteins at: https://www.ebi.ac.uk/pride/archive/projects/{accession} "
            f"(or use pride_find_projects_for_protein to go the other way).")


@mcp.tool()
def pride_find_projects_for_protein(protein: str, limit: int = 15) -> str:
    """Find PRIDE projects associated with a protein (by accession/name keyword).

    Args:
        protein: protein accession or name (e.g. "P04637", "TP53").
        limit: max projects (default 15).
    """
    return pride_search_projects(protein, limit=limit)


# ==================================================================== MetaboLights
@mcp.tool()
def metabolights_list_studies(limit: int = 40) -> str:
    """List public MetaboLights study accessions.

    Args:
        limit: max study ids (default 40).
    """
    j = _get(f"{METABOLIGHTS}/studies")
    ids = j.get("content", []) if isinstance(j, dict) else []
    if not ids:
        return "No MetaboLights studies."
    shown = ids[:max(1, min(limit, MAX_ROWS))]
    return f"# {len(ids)} public studies; showing {len(shown)}\n" + ", ".join(shown)


@mcp.tool()
def metabolights_get_studies(study_id: str) -> str:
    """Get a MetaboLights study's metadata.

    Args:
        study_id: study accession (e.g. "MTBLS1").
    """
    j = _get(f"{METABOLIGHTS}/studies/public/study/{study_id}")
    c = j.get("content", j) if isinstance(j, dict) else {}
    fields = ["title", "description", "studyPublicReleaseDate", "studyStatus", "organism"]
    out = [f"accession: {study_id}"]
    for k in fields:
        v = c.get(k)
        if isinstance(v, (str, int)) and v:
            out.append(f"{k}: {str(v)[:400]}")
    return "\n".join(out) if len(out) > 1 else f"Study {study_id} (metadata under access restriction or empty)."


@mcp.tool()
def metabolights_get_study_files(study_id: str, limit: int = 30) -> str:
    """List the files of a MetaboLights study.

    Args:
        study_id: study accession (e.g. "MTBLS1").
        limit: max files (default 30).
    """
    j = _get(f"{METABOLIGHTS}/studies/{study_id}/files")
    files = j.get("study", []) if isinstance(j, dict) else []
    if not files:
        return f"No files listed for {study_id}."
    rows = [f"# {len(files)} files in {study_id}", "file\ttype\tdirectory"]
    for f in files[:max(1, min(limit, MAX_ROWS))]:
        rows.append(f"{f.get('file','')}\t{f.get('type','')}\t{f.get('directory','')}")
    return _cap(rows, "files")


@mcp.tool()
def metabolights_search_data_files(study_id: str, query: str = "") -> str:
    """Search the data files of a MetaboLights study by filename substring.

    Args:
        study_id: study accession (e.g. "MTBLS1").
        query: filename substring to match (e.g. ".mzML", "sample"); empty for all data files.
    """
    j = _get(f"{METABOLIGHTS}/studies/{study_id}/files")
    files = j.get("study", []) if isinstance(j, dict) else []
    q = query.lower().strip()
    rows = [f"# data files in {study_id}" + (f" matching '{query}'" if q else ""), "file\ttype"]
    for f in files:
        name = f.get("file", "")
        if f.get("directory"):
            continue
        if q and q not in name.lower():
            continue
        rows.append(f"{name}\t{f.get('type','')}")
    return _cap(rows, "files") if len(rows) > 1 else f"No matching data files in {study_id}."


if __name__ == "__main__":
    mcp.run()
