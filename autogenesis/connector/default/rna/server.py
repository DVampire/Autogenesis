#!/usr/bin/env python3
"""RNA MCP server — RNA families over the PUBLIC Rfam API (https://rfam.org), no auth.

Rfam is a database of RNA families represented by multiple-sequence alignments,
consensus secondary structures, and covariance models.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import time

import requests
from mcp.server.fastmcp import FastMCP

RFAM = "https://rfam.org"
HDRS = {"User-Agent": "Autogenesis-rna/1.0", "Accept": "application/json"}
JSONP = {"content-type": "application/json"}
TIMEOUT = 30
MAX_CHARS = 3000

mcp = FastMCP("rna")


def _json(path, **params):
    r = requests.get(f"{RFAM}{path}", params={**JSONP, **params}, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"Rfam {path} -> {r.status_code}")
    return r.json()


def _text(path, **params):
    r = requests.get(f"{RFAM}{path}", params=params, headers={"User-Agent": HDRS["User-Agent"]}, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"Rfam {path} -> {r.status_code}")
    return r.text


def _cap_text(txt: str, label: str) -> str:
    if len(txt) > MAX_CHARS:
        return txt[:MAX_CHARS] + f"\n... ({len(txt)} chars total; {label} truncated — download the full file from Rfam)"
    return txt


# --------------------------------------------------------------------------- #
@mcp.tool()
def get_family(accession: str) -> str:
    """Get an Rfam family's metadata (id, description, type, clan, curation).

    Args:
        accession: Rfam accession (e.g. "RF00001") or family id (e.g. "5S_rRNA").
    """
    rf = _json(f"/family/{accession}").get("rfam", {})
    if not rf:
        return f"No Rfam family {accession}."
    cm = rf.get("cm", {})
    build = cm.get("build_command", "") if isinstance(cm, dict) else ""
    clan = rf.get("clan")
    clan = (clan.get("id") or clan.get("acc")) if isinstance(clan, dict) else clan
    return (f"accession: {rf.get('acc','')}\nid: {rf.get('id','')}\ndescription: {rf.get('description','')}\n"
            f"clan: {clan or '(none)'}\ncomment: {(rf.get('comment') or '')[:300]}\n"
            f"curation: {rf.get('curation','')}\ncm_build: {build}")


@mcp.tool()
def get_seed_alignment(accession: str) -> str:
    """Get an Rfam family's seed alignment (Stockholm format, truncated).

    Args:
        accession: Rfam accession (e.g. "RF00001").
    """
    return _cap_text(_text(f"/family/{accession}/alignment", type="seed"), "alignment")


@mcp.tool()
def get_covariance_model(accession: str) -> str:
    """Get an Rfam family's covariance model (CM) file header (truncated).

    Args:
        accession: Rfam accession (e.g. "RF00001").
    """
    return _cap_text(_text(f"/family/{accession}/cm"), "covariance model")


@mcp.tool()
def get_tree(accession: str) -> str:
    """Get an Rfam family's phylogenetic tree (Newick, truncated).

    Args:
        accession: Rfam accession (e.g. "RF00001").
    """
    return _cap_text(_text(f"/family/{accession}/tree"), "tree")


@mcp.tool()
def get_sequence_regions(accession: str) -> str:
    """Sequence regions (genomic hits) of an Rfam family.

    NOTE: Rfam restricts the full-region web API; bulk regions are distributed via FTP.

    Args:
        accession: Rfam accession (e.g. "RF00001").
    """
    try:
        data = _json(f"/family/{accession}/regions")
        return str(data)[:MAX_CHARS]
    except RuntimeError:
        return (f"Rfam does not serve full sequence regions for {accession} over the web API. "
                f"Download them from FTP: https://ftp.ebi.ac.uk/pub/databases/Rfam/CURRENT/ "
                f"(Rfam.full_region.gz), or use get_structure_mapping for PDB structure hits.")


@mcp.tool()
def get_structure_mapping(accession: str, limit: int = 25) -> str:
    """Map an Rfam family to 3D structures (PDB) — CM-to-PDB region mappings.

    Args:
        accession: Rfam accession (e.g. "RF00001").
        limit: max mappings (default 25).
    """
    mapping = _json(f"/family/{accession}/structures").get("mapping", [])
    if not mapping:
        return f"No PDB structure mappings for {accession}."
    rows = [f"# {len(mapping)} PDB mappings for {accession}", "pdb_id\tchain\tcm_range\tpdb_range\tbit_score\tevalue"]
    for m in mapping[:max(1, limit)]:
        rows.append(f"{m.get('pdb_id','')}\t{m.get('chain','')}\t{m.get('cm_start','')}-{m.get('cm_end','')}\t"
                    f"{m.get('pdb_start','')}-{m.get('pdb_end','')}\t{m.get('bit_score','')}\t{m.get('evalue_score','')}")
    if len(rows) > limit + 2:
        rows = rows[:limit + 2] + [f"... ({len(mapping) - limit} more)"]
    return "\n".join(rows)


@mcp.tool()
def accession_to_id(accession: str) -> str:
    """Convert an Rfam accession to its family id.

    Args:
        accession: Rfam accession (e.g. "RF00001").
    """
    rf = _json(f"/family/{accession}").get("rfam", {})
    return f"{rf.get('acc','')} -> {rf.get('id','')}" if rf else f"No Rfam family {accession}."


@mcp.tool()
def id_to_accession(rfam_id: str) -> str:
    """Convert an Rfam family id to its accession.

    Args:
        rfam_id: Rfam family id (e.g. "5S_rRNA").
    """
    rf = _json(f"/family/{rfam_id}").get("rfam", {})
    return f"{rf.get('id','')} -> {rf.get('acc','')}" if rf else f"No Rfam family {rfam_id}."


@mcp.tool()
def search_sequence(sequence: str, max_wait: int = 25) -> str:
    """Search a nucleotide sequence against Rfam covariance models (Infernal cmscan).

    Args:
        sequence: RNA/DNA sequence (plain letters, no FASTA header needed).
        max_wait: seconds to wait for the async job (default 25).
    """
    try:
        sub = requests.post(f"{RFAM}/search/sequence",
                            headers={"User-Agent": HDRS["User-Agent"], "Accept": "application/json"},
                            data={"seq": sequence.strip()}, timeout=TIMEOUT)
        if sub.status_code >= 400 or not sub.headers.get("content-type", "").startswith("application/json"):
            raise RuntimeError(f"submit status {sub.status_code}")
        result_url = sub.json().get("resultURL")
        if not result_url:
            raise RuntimeError("no resultURL")
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(4)
            rr = requests.get(result_url, headers=HDRS, timeout=TIMEOUT)
            if rr.status_code == 200 and rr.headers.get("content-type", "").startswith("application/json"):
                hits = rr.json().get("hits", {})
                rows = ["family\taccession\tevalue\tstart\tend\tstrand"]
                for fam, lst in (hits.items() if isinstance(hits, dict) else []):
                    for h in lst:
                        rows.append(f"{fam}\t{h.get('acc','')}\t{h.get('E','')}\t{h.get('start','')}\t{h.get('end','')}\t{h.get('strand','')}")
                return "\n".join(rows) if len(rows) > 1 else "No Rfam family hits for this sequence."
        return "Rfam sequence search is still running (async cmscan); try again with a larger max_wait."
    except Exception as e:
        return (f"Rfam sequence search is temporarily unavailable ({type(e).__name__}). "
                f"The Rfam online search (Infernal cmscan) can be rate-limited; retry, or run cmscan "
                f"locally with the family CM from get_covariance_model.")


if __name__ == "__main__":
    mcp.run()
