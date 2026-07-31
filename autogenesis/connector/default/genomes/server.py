#!/usr/bin/env python3
"""Genomes MCP server — genome annotation over the PUBLIC Ensembl REST API
(rest.ensembl.org) and the PUBLIC UCSC Genome Browser REST API
(api.genome.ucsc.edu), no auth: gene lookup, xrefs, VEP, homology, sequence,
overlap, plus UCSC track listing/data, conservation and TFBS clusters.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

ENSEMBL = "https://rest.ensembl.org"
# UCSC REST API. The dedicated api.genome.ucsc.edu host is canonical; the identical
# hubApi endpoints on the main and European mirrors are tried as fallbacks so a
# single unreachable host does not disable the UCSC tools.
UCSC_HOSTS = [
    "https://api.genome.ucsc.edu",
    "https://genome.ucsc.edu/cgi-bin/hubApi",
    "https://genome-euro.ucsc.edu/cgi-bin/hubApi",
]
HDRS = {"User-Agent": "Autogenesis-genomes/1.0", "Accept": "application/json"}
TIMEOUT = 30
MAX_ROWS = 60

_SPECIES = {"human": "homo_sapiens", "mouse": "mus_musculus", "rat": "rattus_norvegicus",
            "zebrafish": "danio_rerio", "fly": "drosophila_melanogaster"}

mcp = FastMCP("genomes")


def _ens(path, **params):
    r = requests.get(f"{ENSEMBL}{path}", params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"Ensembl {path} -> {r.status_code}: {r.text[:200]}")
    return r.json()


def _ucsc(path, **params):
    last = None
    for host in UCSC_HOSTS:
        try:
            r = requests.get(f"{host}{path}", params=params, headers=HDRS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = f"{host}: {e}"
            continue
    raise RuntimeError(f"UCSC {path} failed on all mirrors ({last})")


def _parse_region(region: str):
    """Parse 'chrom:start-end' (1-based, inclusive) into (chrom, start0, end).

    UCSC getData/track uses 0-based half-open coordinates, so we convert the
    1-based start. Accepts an optional 'chr' prefix either way.
    """
    m = re.match(r"^(\w+):([\d,]+)-([\d,]+)$", region.strip())
    if not m:
        raise ValueError(f"region must be 'chrom:start-end', got '{region}'")
    chrom, start, end = m.group(1), int(m.group(2).replace(",", "")), int(m.group(3).replace(",", ""))
    if not chrom.startswith("chr"):
        chrom = "chr" + chrom
    return chrom, max(0, start - 1), end


def _track_rows(payload: dict, track: str):
    """Extract the list of feature rows from a UCSC getData/track response.

    The rows live under a key named after the track (or its container); fall back
    to the first list-valued key that is not chromosome/size metadata.
    """
    if track in payload and isinstance(payload[track], list):
        return payload[track]
    for k, v in payload.items():
        if isinstance(v, list):
            return v
    return []


def _sp(species: str) -> str:
    return _SPECIES.get(species.lower(), species)


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ================================================================= Ensembl
@mcp.tool()
def ensembl_lookup(query: str, species: str = "human") -> str:
    """Look up a gene/transcript by Ensembl id or gene symbol.

    Args:
        query: Ensembl id (e.g. "ENSG00000012048") or gene symbol (e.g. "BRCA1").
        species: species for symbol lookup (default "human").
    """
    if query.upper().startswith("ENS"):
        d = _ens(f"/lookup/id/{query}", expand=0)
    else:
        d = _ens(f"/lookup/symbol/{_sp(species)}/{query}", expand=0)
    if not d:
        return f"No Ensembl record for '{query}'."
    keys = ["id", "display_name", "biotype", "seq_region_name", "start", "end", "strand", "description"]
    return "\n".join(f"{k}: {d.get(k)}" for k in keys if d.get(k) is not None)


@mcp.tool()
def ensembl_xrefs(query: str, species: str = "human") -> str:
    """Cross-references (external DB ids) for a gene via Ensembl.

    Args:
        query: Ensembl id or gene symbol (e.g. "BRCA1").
        species: species for symbol lookup (default "human").
    Returns 'db<TAB>primary_id<TAB>display_id' rows.
    """
    if query.upper().startswith("ENS"):
        ens_id = query
    else:
        hit = _ens(f"/lookup/symbol/{_sp(species)}/{query}", expand=0)
        ens_id = hit.get("id") if hit else None
    if not ens_id:
        return f"Could not resolve '{query}'."
    data = _ens(f"/xrefs/id/{ens_id}")
    rows = ["db\tprimary_id\tdisplay_id"]
    for x in (data if isinstance(data, list) else []):
        rows.append(f"{x.get('dbname','')}\t{x.get('primary_id','')}\t{x.get('display_id','')}")
    return _cap(rows, "xrefs") if len(rows) > 1 else f"No xrefs for {ens_id}."


@mcp.tool()
def ensembl_vep_variant(variant: str, species: str = "human") -> str:
    """Predict variant effects (VEP) for an rsID, HGVS notation, or region/allele.

    Args:
        variant: dbSNP rsID (e.g. "rs699"), HGVS (e.g. "ENST00000269305.4:c.215C>G"),
            or region:allele (e.g. "17:43044295:A").
        species: species (default "human").
    """
    v = variant.strip()
    if v.lower().startswith("rs"):
        data = _ens(f"/vep/{species}/id/{v}")
    else:
        data = _ens(f"/vep/{species}/hgvs/{v}")
    if not data:
        return f"No VEP result for '{variant}'."
    d = data[0]
    out = [f"input: {d.get('input', variant)}", f"most_severe_consequence: {d.get('most_severe_consequence')}",
           f"location: {d.get('seq_region_name')}:{d.get('start')}-{d.get('end')}"]
    tcs = d.get("transcript_consequences") or []
    if tcs:
        out.append("transcript_consequences (sample):")
        for tc in tcs[:8]:
            out.append(f"  {tc.get('gene_symbol','')}\t{tc.get('transcript_id','')}\t"
                       f"{','.join(tc.get('consequence_terms', []))}\t{tc.get('impact','')}")
    return "\n".join(out)


@mcp.tool()
def ensembl_homology(gene: str, species: str = "human", target_species: str = "") -> str:
    """Orthologues of a gene across species via Ensembl Compara.

    Args:
        gene: gene symbol (e.g. "BRCA1").
        species: source species (default "human").
        target_species: optional single target species to restrict to (e.g. "mouse").
    """
    params = {"type": "orthologues", "format": "condensed"}
    if target_species.strip():
        params["target_species"] = _sp(target_species)
    data = _ens(f"/homology/symbol/{_sp(species)}/{gene}", **params).get("data", [])
    homs = data[0].get("homologies", []) if data else []
    if not homs:
        return f"No orthologues for {gene}."
    rows = [f"# orthologues of {gene}", "homolog_id\tspecies\ttype"]
    for h in homs:
        rows.append(f"{h.get('id','')}\t{h.get('species','')}\t{h.get('type','')}")
    return _cap(rows, "orthologues")


@mcp.tool()
def ensembl_sequence(ensembl_id: str, seq_type: str = "genomic", max_len: int = 1000) -> str:
    """Fetch the sequence for an Ensembl id.

    Args:
        ensembl_id: gene/transcript/protein id (e.g. "ENST00000357654").
        seq_type: "genomic", "cds", "cdna", or "protein" (default "genomic").
        max_len: max sequence characters to return (default 1000; full length reported).
    """
    d = _ens(f"/sequence/id/{ensembl_id}", type=seq_type)
    seq = d.get("seq", "") if isinstance(d, dict) else ""
    if not seq:
        return f"No {seq_type} sequence for {ensembl_id}."
    body = seq[:max(1, max_len)]
    more = f"\n... (total {len(seq)} bp/aa; showing {len(body)})" if len(seq) > len(body) else ""
    return f"# {ensembl_id} ({seq_type}), length {len(seq)}\n{body}{more}"


@mcp.tool()
def ensembl_overlap_region(region: str, species: str = "human", feature: str = "gene") -> str:
    """List features overlapping a genomic region via Ensembl.

    Args:
        region: "chrom:start-end" (e.g. "17:43044295-43125483").
        species: species (default "human").
        feature: feature type — gene, transcript, exon, variation, regulatory (default "gene").
    """
    data = _ens(f"/overlap/region/{_sp(species)}/{region}", feature=feature)
    if not isinstance(data, list) or not data:
        return f"No {feature} features in {region}."
    rows = [f"# {feature} features in {region}", "name\tid\tbiotype\tstart\tend"]
    for f in data:
        rows.append(f"{f.get('external_name', f.get('id',''))}\t{f.get('id','')}\t"
                    f"{f.get('biotype','')}\t{f.get('start','')}\t{f.get('end','')}")
    return _cap(rows, "features")


# ================================================================= UCSC
@mcp.tool()
def ucsc_list_tracks(genome: str = "hg38", search: str = "") -> str:
    """List queryable data tracks for a UCSC assembly.

    Args:
        genome: UCSC assembly (e.g. "hg38", "hg19", "mm39").
        search: optional case-insensitive substring to filter by track name/label.
    Returns 'track<TAB>type<TAB>shortLabel' rows (composite subtracks flattened).
    """
    data = _ucsc("/list/tracks", genome=genome)
    groups = data.get(genome, data)
    rows = [f"# UCSC tracks for {genome}", "track\ttype\tshortLabel"]

    def emit(name, meta):
        if not isinstance(meta, dict):
            return
        label = meta.get("shortLabel", meta.get("longLabel", ""))
        typ = meta.get("type", "")
        if not search or search.lower() in name.lower() or search.lower() in label.lower():
            rows.append(f"{name}\t{typ}\t{label}")
        # composite/super tracks nest their members as further dict entries
        for k, v in meta.items():
            if isinstance(v, dict) and ("type" in v or "shortLabel" in v):
                emit(k, v)

    for name, meta in groups.items():
        emit(name, meta)
    if len(rows) <= 2:
        return f"No tracks for {genome}."
    return "\n".join(rows[:2]) + "\n" + _cap(rows[2:], "tracks")


@mcp.tool()
def ucsc_track_data(track: str, region: str, genome: str = "hg38") -> str:
    """Fetch raw row data for any UCSC track within a genomic region.

    Args:
        track: UCSC track name (see ucsc_list_tracks), e.g. "refGene", "knownGene".
        region: "chrom:start-end" (1-based), e.g. "chr17:43044295-43125483".
        genome: UCSC assembly (default "hg38").
    Returns one line per feature with its raw JSON fields.
    """
    chrom, start, end = _parse_region(region)
    data = _ucsc("/getData/track", genome=genome, track=track, chrom=chrom, start=start, end=end)
    rows = _track_rows(data, track)
    if not rows:
        return f"No {track} rows in {region} ({genome})."
    out = [f"# {track} in {chrom}:{start}-{end} ({genome}) — {len(rows)} rows"]
    for r in rows[:MAX_ROWS]:
        if isinstance(r, dict):
            keys = [k for k in ("chrom", "chromStart", "chromEnd", "start", "end",
                                "name", "name2", "score", "strand", "value") if k in r]
            out.append("\t".join(f"{k}={r[k]}" for k in keys) or str(r))
        else:
            out.append(str(r))
    if len(rows) > MAX_ROWS:
        out.append(f"... ({len(rows) - MAX_ROWS} more rows truncated)")
    return "\n".join(out)


@mcp.tool()
def ucsc_conservation(region: str, genome: str = "hg38", track: str = "") -> str:
    """Summarize evolutionary conservation across a region from UCSC phyloP/phastCons.

    Args:
        region: "chrom:start-end" (1-based), e.g. "chr17:43044295-43044395".
        genome: UCSC assembly (default "hg38").
        track: conservation bigWig track; defaults to "phyloP100way" for hg38,
            "phyloP60way" otherwise. Try "phastCons100way" for phastCons scores.
    Returns per-track count/mean/min/max of the base-level scores in the region.
    """
    chrom, start, end = _parse_region(region)
    if not track:
        track = "phyloP100way" if genome == "hg38" else "phyloP60way"
    data = _ucsc("/getData/track", genome=genome, track=track, chrom=chrom, start=start, end=end)
    rows = _track_rows(data, track)
    values = []
    for r in rows:
        if isinstance(r, dict) and r.get("value") is not None:
            try:
                values.append(float(r["value"]))
            except (TypeError, ValueError):
                pass
    if not values:
        return (f"No conservation values for track '{track}' in {region} ({genome}). "
                f"Check the track name with ucsc_list_tracks(search='cons').")
    n = len(values)
    return (f"# conservation ({track}) over {chrom}:{start}-{end} ({genome})\n"
            f"positions: {n}\nmean: {sum(values)/n:.4f}\n"
            f"min: {min(values):.4f}\nmax: {max(values):.4f}")


@mcp.tool()
def ucsc_tfbs_clusters(region: str, genome: str = "hg38") -> str:
    """List ENCODE transcription-factor binding-site (TFBS) clusters in a region.

    Uses UCSC's ENCODE TF ChIP-seq clustered track (encRegTfbsClustered on hg38 /
    hg19). Summarizes the factors bound and their peak scores.

    Args:
        region: "chrom:start-end" (1-based), e.g. "chr17:43044295-43125483".
        genome: UCSC assembly (default "hg38"; supported on hg38/hg19).
    """
    chrom, start, end = _parse_region(region)
    track = "encRegTfbsClustered"
    data = _ucsc("/getData/track", genome=genome, track=track, chrom=chrom, start=start, end=end)
    rows = _track_rows(data, track)
    if not rows:
        return (f"No ENCODE TFBS clusters in {region} ({genome}). "
                f"This track is available on hg38 and hg19.")
    out = [f"# ENCODE TFBS clusters in {chrom}:{start}-{end} ({genome}) — {len(rows)} sites",
           "factor\tchromStart\tchromEnd\tscore"]
    for r in rows[:MAX_ROWS]:
        if isinstance(r, dict):
            out.append(f"{r.get('name','')}\t{r.get('chromStart','')}\t"
                       f"{r.get('chromEnd','')}\t{r.get('score','')}")
    if len(rows) > MAX_ROWS:
        out.append(f"... ({len(rows) - MAX_ROWS} more sites truncated)")
    return "\n".join(out)


@mcp.tool()
def ucsc_chrom_sizes(genome: str = "hg38", search: str = "") -> str:
    """Get chromosome/contig names and sizes for a UCSC assembly.

    Args:
        genome: UCSC assembly (e.g. "hg38", "hg19", "mm39").
        search: optional substring to filter chromosome names (e.g. "chr1").
    Returns 'chrom<TAB>size(bp)' rows, largest first.
    """
    data = _ucsc("/list/chromosomes", genome=genome)
    chroms = data.get("chromosomes", {})
    if not chroms:
        return f"No chromosome data for {genome}."
    items = [(c, s) for c, s in chroms.items() if not search or search.lower() in c.lower()]
    items.sort(key=lambda x: x[1], reverse=True)
    rows = [f"# {genome}: {data.get('chromCount', len(chroms))} sequences", "chrom\tsize"]
    rows += [f"{c}\t{s}" for c, s in items]
    return "\n".join(rows[:2]) + "\n" + _cap(rows[2:], "sequences")


if __name__ == "__main__":
    mcp.run()
