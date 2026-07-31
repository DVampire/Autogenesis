#!/usr/bin/env python3
"""cBioPortal MCP server — a self-contained wrapper over the PUBLIC cBioPortal REST
API (https://www.cbioportal.org/api). Cancer genomics cohorts: studies, mutations,
copy-number alterations, and clinical attributes. No authentication.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://www.cbioportal.org/api"
TIMEOUT = 60
MAX_ROWS = 400

mcp = FastMCP("cbioportal")


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _get(path: str, **params):
    r = requests.get(BASE + path, params=params, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"cBioPortal GET {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _post(path: str, body, **params):
    r = requests.post(BASE + path, params=params, json=body, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"cBioPortal POST {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _resolve_gene(gene: str) -> int:
    """Resolve a Hugo symbol or Entrez ID to an Entrez gene ID."""
    info = _get(f"/genes/{gene}")
    return int(info["entrezGeneId"])


def _resolve_profile(study_id: str, alteration_type: str, datatype: Optional[str] = None) -> str:
    """Find the molecular-profile id for an alteration type (e.g. MUTATION_EXTENDED)."""
    for m in _get(f"/studies/{study_id}/molecular-profiles"):
        if m.get("molecularAlterationType") == alteration_type and (
            datatype is None or m.get("datatype") == datatype
        ):
            return m["molecularProfileId"]
    raise RuntimeError(
        f"Study '{study_id}' has no {alteration_type}"
        f"{'/' + datatype if datatype else ''} profile."
    )


def _cap(rows: list[str], scope: str) -> str:
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def cbioportal_list_studies(keyword: str = "", limit: int = 50) -> str:
    """List cancer studies (cohorts), optionally filtered by a keyword.

    Args:
        keyword: filter studies by name/id (e.g. "glioblastoma", "breast", "tcga").
        limit: max studies to return (default 50).
    Returns 'studyId<TAB>name<TAB>samples' rows.
    """
    params = {"projection": "SUMMARY", "pageSize": max(1, min(limit, MAX_ROWS)), "direction": "ASC"}
    if keyword.strip():
        params["keyword"] = keyword.strip()
    studies = _get("/studies", **params)
    rows = ["studyId\tname\tsamples"]
    for s in studies:
        rows.append(f"{s.get('studyId','')}\t{s.get('name','')}\t{s.get('allSampleCount','')}")
    return _cap(rows, "studies") if len(rows) > 1 else "No studies found."


@mcp.tool()
def cbioportal_get_study(study_id: str) -> str:
    """Get metadata for one study (name, cancer type, sample count, citation).

    Args:
        study_id: e.g. "gbm_tcga_pan_can_atlas_2018" (from cbioportal_list_studies).
    """
    s = _get(f"/studies/{study_id}")
    fields = ["studyId", "name", "description", "cancerTypeId", "allSampleCount",
              "pmid", "citation"]
    return "\n".join(f"{k}: {s.get(k)}" for k in fields if s.get(k) is not None)


@mcp.tool()
def cbioportal_mutations_in_gene(study_id: str, gene: str, sample_list_id: str = "") -> str:
    """List mutations of a gene across the samples in a study.

    Args:
        study_id: e.g. "gbm_tcga_pan_can_atlas_2018".
        gene: Hugo symbol or Entrez ID (e.g. "TP53").
        sample_list_id: sample list (default "<study_id>_all").
    Returns 'sampleId<TAB>proteinChange<TAB>mutationType' rows.
    """
    entrez = _resolve_gene(gene)
    profile = _resolve_profile(study_id, "MUTATION_EXTENDED")
    sl = sample_list_id.strip() or f"{study_id}_all"
    muts = _post(f"/molecular-profiles/{profile}/mutations/fetch",
                 {"sampleListId": sl, "entrezGeneIds": [entrez]}, projection="DETAILED")
    rows = ["sampleId\tproteinChange\tmutationType"]
    for m in muts:
        rows.append(f"{m.get('sampleId','')}\t{m.get('proteinChange','')}\t{m.get('mutationType','')}")
    if len(rows) == 1:
        return f"No {gene} mutations found in {study_id}."
    return _cap(rows, "mutations")


@mcp.tool()
def cbioportal_mutation_frequency(study_id: str, gene: str, sample_list_id: str = "") -> str:
    """Compute how often a gene is mutated in a study (mutated samples / total).

    Args:
        study_id: e.g. "gbm_tcga_pan_can_atlas_2018".
        gene: Hugo symbol or Entrez ID (e.g. "TP53").
        sample_list_id: sample list (default "<study_id>_all").
    """
    entrez = _resolve_gene(gene)
    profile = _resolve_profile(study_id, "MUTATION_EXTENDED")
    sl = sample_list_id.strip() or f"{study_id}_all"
    muts = _post(f"/molecular-profiles/{profile}/mutations/fetch",
                 {"sampleListId": sl, "entrezGeneIds": [entrez]}, projection="ID")
    mutated = {m.get("sampleId") for m in muts}
    total = len(_get(f"/sample-lists/{sl}").get("sampleIds", []))
    freq = (len(mutated) / total * 100) if total else 0.0
    return (f"gene: {gene}\nstudy: {study_id}\nmutated_samples: {len(mutated)}\n"
            f"total_samples: {total}\nfrequency: {freq:.1f}%")


@mcp.tool()
def cbioportal_cna_in_gene(study_id: str, gene: str, event_type: str = "HOMDEL_AND_AMP") -> str:
    """List discrete copy-number alterations of a gene across a study's samples.

    Args:
        study_id: e.g. "gbm_tcga_pan_can_atlas_2018".
        gene: Hugo symbol or Entrez ID (e.g. "EGFR").
        event_type: one of ALL, AMP, HOMDEL, HOMDEL_AND_AMP, GAIN, HETLOSS, DIPLOID
            (default HOMDEL_AND_AMP — the clinically significant events).
    Returns 'sampleId<TAB>alteration' rows (-2 HOMDEL, -1 HETLOSS, 1 GAIN, 2 AMP).
    """
    entrez = _resolve_gene(gene)
    profile = _resolve_profile(study_id, "COPY_NUMBER_ALTERATION", "DISCRETE")
    sl = f"{study_id}_all"
    cnas = _post(f"/molecular-profiles/{profile}/discrete-copy-number/fetch",
                 {"sampleListId": sl, "entrezGeneIds": [entrez]},
                 discreteCopyNumberEventType=event_type, projection="SUMMARY")
    label = {-2: "HOMDEL", -1: "HETLOSS", 0: "DIPLOID", 1: "GAIN", 2: "AMP"}
    rows = ["sampleId\talteration"]
    for c in cnas:
        a = c.get("alteration")
        rows.append(f"{c.get('sampleId','')}\t{a} ({label.get(a, a)})")
    if len(rows) == 1:
        return f"No {event_type} CNA events for {gene} in {study_id}."
    return _cap(rows, "CNA events")


@mcp.tool()
def cbioportal_clinical_attributes(study_id: str) -> str:
    """List the clinical attributes recorded for a study's patients/samples.

    Args:
        study_id: e.g. "gbm_tcga_pan_can_atlas_2018".
    Returns 'attributeId<TAB>displayName<TAB>datatype' rows.
    """
    attrs = _get(f"/studies/{study_id}/clinical-attributes")
    rows = ["attributeId\tdisplayName\tdatatype"]
    for a in attrs:
        rows.append(f"{a.get('clinicalAttributeId','')}\t{a.get('displayName','')}\t{a.get('datatype','')}")
    return _cap(rows, "attributes")


if __name__ == "__main__":
    mcp.run()
