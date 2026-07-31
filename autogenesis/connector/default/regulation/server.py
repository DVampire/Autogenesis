#!/usr/bin/env python3
"""Regulation MCP server — gene-regulation resources over PUBLIC APIs, no auth:

  * ENCODE  (encodeproject.org)  — experiments, files, biosamples
  * JASPAR  (jaspar.elixir.no)   — transcription-factor binding matrices
  * UniBind (unibind.uio.no)     — TF binding site (TFBS) datasets

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import requests
from mcp.server.fastmcp import FastMCP

ENCODE = "https://www.encodeproject.org"
JASPAR = "https://jaspar.elixir.no/api/v1"
UNIBIND = "https://unibind.uio.no/api/v1"
HDRS = {"User-Agent": "Autogenesis-regulation/1.0", "Accept": "application/json"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("regulation")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ==================================================================== ENCODE
@mcp.tool()
def encode_search_experiments(query: str, limit: int = 15) -> str:
    """Search ENCODE experiments by keyword (assay, target, biosample).

    Args:
        query: search text (e.g. "CTCF K562 ChIP-seq").
        limit: max experiments (default 15).
    """
    j = _get(f"{ENCODE}/search/", type="Experiment", searchTerm=query, format="json",
             limit=max(1, min(limit, MAX_ROWS)))
    hits = j.get("@graph", [])
    if not hits:
        return f"No ENCODE experiments for '{query}'."
    rows = [f"# {j.get('total','?')} experiments; showing {len(hits)}", "accession\tassay\ttarget\tbiosample"]
    for x in hits:
        tgt = (x.get("target") or {}).get("label", "") if isinstance(x.get("target"), dict) else ""
        bs = (x.get("biosample_ontology") or {}).get("term_name", "") if isinstance(x.get("biosample_ontology"), dict) else ""
        rows.append(f"{x.get('accession','')}\t{x.get('assay_title','')}\t{tgt}\t{bs}")
    return _cap(rows, "experiments")


@mcp.tool()
def encode_search_biosamples(query: str, limit: int = 15) -> str:
    """Search ENCODE biosamples by keyword.

    Args:
        query: search text (e.g. "K562", "liver").
        limit: max biosamples (default 15).
    """
    j = _get(f"{ENCODE}/search/", type="Biosample", searchTerm=query, format="json",
             limit=max(1, min(limit, MAX_ROWS)))
    hits = j.get("@graph", [])
    if not hits:
        return f"No ENCODE biosamples for '{query}'."
    rows = ["accession\tterm\torganism"]
    for x in hits:
        term = (x.get("biosample_ontology") or {}).get("term_name", "") if isinstance(x.get("biosample_ontology"), dict) else x.get("summary", "")
        org = (x.get("organism") or {}).get("scientific_name", "") if isinstance(x.get("organism"), dict) else ""
        rows.append(f"{x.get('accession','')}\t{term}\t{org}")
    return _cap(rows, "biosamples")


@mcp.tool()
def encode_list_files(experiment_accession: str, limit: int = 25) -> str:
    """List the files produced by an ENCODE experiment.

    Args:
        experiment_accession: e.g. "ENCSR000AKB".
        limit: max files (default 25).
    """
    j = _get(f"{ENCODE}/search/", type="File", dataset=f"/experiments/{experiment_accession}/",
             format="json", limit=max(1, min(limit, MAX_ROWS)))
    hits = j.get("@graph", [])
    if not hits:
        return f"No files for experiment {experiment_accession}."
    rows = [f"# {j.get('total','?')} files in {experiment_accession}", "accession\tformat\toutput_type\tstatus"]
    for f in hits:
        rows.append(f"{f.get('accession','')}\t{f.get('file_format','')}\t{f.get('output_type','')}\t{f.get('status','')}")
    return _cap(rows, "files")


@mcp.tool()
def encode_get_experiment(accession: str) -> str:
    """Get an ENCODE experiment's metadata.

    Args:
        accession: experiment accession (e.g. "ENCSR000AKB").
    """
    x = _get(f"{ENCODE}/experiments/{accession}/", format="json")
    tgt = (x.get("target") or {}).get("label", "") if isinstance(x.get("target"), dict) else ""
    bs = (x.get("biosample_ontology") or {}).get("term_name", "") if isinstance(x.get("biosample_ontology"), dict) else ""
    return (f"accession: {x.get('accession','')}\nassay: {x.get('assay_title','')}\ntarget: {tgt}\n"
            f"biosample: {bs}\nlab: {(x.get('lab') or {}).get('title','') if isinstance(x.get('lab'),dict) else ''}\n"
            f"status: {x.get('status','')}\nfiles: {len(x.get('files',[]))}\ndescription: {(x.get('description') or '')[:300]}")


@mcp.tool()
def encode_get_file(accession: str) -> str:
    """Get an ENCODE file's metadata (format, type, assembly, download URL).

    Args:
        accession: file accession (e.g. "ENCFF000ABC").
    """
    f = _get(f"{ENCODE}/files/{accession}/", format="json")
    return (f"accession: {f.get('accession','')}\nfile_format: {f.get('file_format','')}\n"
            f"output_type: {f.get('output_type','')}\nassembly: {f.get('assembly','')}\n"
            f"file_size: {f.get('file_size','')}\nstatus: {f.get('status','')}\n"
            f"download: {ENCODE}{f.get('href','')}")


@mcp.tool()
def encode_get_biosample(accession: str) -> str:
    """Get an ENCODE biosample's metadata.

    Args:
        accession: biosample accession (e.g. "ENCBS000AAA").
    """
    b = _get(f"{ENCODE}/biosamples/{accession}/", format="json")
    org = (b.get("organism") or {}).get("scientific_name", "") if isinstance(b.get("organism"), dict) else ""
    term = (b.get("biosample_ontology") or {}).get("term_name", "") if isinstance(b.get("biosample_ontology"), dict) else ""
    return (f"accession: {b.get('accession','')}\nterm: {term}\norganism: {org}\n"
            f"type: {b.get('biosample_ontology',{}).get('classification','') if isinstance(b.get('biosample_ontology'),dict) else ''}\n"
            f"status: {b.get('status','')}\nsummary: {(b.get('summary') or '')[:300]}")


# ==================================================================== JASPAR
@mcp.tool()
def jaspar_get_matrix(matrix_id: str) -> str:
    """Get a JASPAR TF binding matrix (motif) by id.

    Args:
        matrix_id: JASPAR matrix id (e.g. "MA0139.1").
    """
    m = _get(f"{JASPAR}/matrix/{matrix_id}/")
    return (f"matrix_id: {m.get('matrix_id','')}\nname: {m.get('name','')}\n"
            f"collection: {m.get('collection','')}\ntf_class: {', '.join(m.get('class') or [])}\n"
            f"tf_family: {', '.join(m.get('family') or [])}\nspecies: {', '.join(s.get('name','') for s in (m.get('species') or []))}\n"
            f"data_type: {m.get('type','')}")


@mcp.tool()
def jaspar_matrix_versions(base_id: str) -> str:
    """List all versions of a JASPAR matrix.

    Args:
        base_id: JASPAR base id without version (e.g. "MA0139").
    """
    j = _get(f"{JASPAR}/matrix/{base_id}/versions/")
    res = j.get("results", j if isinstance(j, list) else [])
    rows = ["matrix_id\tname\tversion"] + [f"{m.get('matrix_id','')}\t{m.get('name','')}\t{m.get('version','')}" for m in res]
    return "\n".join(rows) if len(rows) > 1 else f"No versions for {base_id}."


@mcp.tool()
def jaspar_list_matrices(search: str = "", collection: str = "", limit: int = 20) -> str:
    """List/search JASPAR matrices, optionally by keyword or collection.

    Args:
        search: TF name/keyword (optional).
        collection: JASPAR collection (e.g. "CORE"), optional.
        limit: max matrices (default 20).
    """
    params = {"page_size": max(1, min(limit, MAX_ROWS))}
    if search.strip():
        params["search"] = search.strip()
    if collection.strip():
        params["collection"] = collection.strip()
    j = _get(f"{JASPAR}/matrix/", **params)
    res = j.get("results", [])
    rows = [f"# {j.get('count','?')} matrices", "matrix_id\tname\tcollection"]
    for m in res:
        rows.append(f"{m.get('matrix_id','')}\t{m.get('name','')}\t{m.get('collection','')}")
    return _cap(rows, "matrices") if len(rows) > 1 else "No matrices found."


def _list(endpoint: str, label: str, fields: tuple, limit: int) -> str:
    j = _get(f"{JASPAR}/{endpoint}/", page_size=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", j if isinstance(j, list) else [])
    if not res:
        return f"No {label}."
    rows = ["\t".join(fields)]
    for x in res[:limit]:
        rows.append("\t".join(str(x.get(f, "")) for f in fields))
    return _cap(rows, label)


@mcp.tool()
def jaspar_list_species(limit: int = 30) -> str:
    """List species available in JASPAR. Args: `limit`."""
    return _list("species", "species", ("tax_id", "species"), limit)


@mcp.tool()
def jaspar_list_taxa(limit: int = 30) -> str:
    """List taxonomic groups in JASPAR. Args: `limit`."""
    return _list("taxon", "taxa", ("name",), limit)


@mcp.tool()
def jaspar_list_collections(limit: int = 30) -> str:
    """List JASPAR matrix collections (e.g. CORE, CNE). Args: `limit`."""
    return _list("collections", "collections", ("name",), limit)


@mcp.tool()
def jaspar_list_releases(limit: int = 30) -> str:
    """List JASPAR database releases. Args: `limit`."""
    return _list("releases", "releases", ("release_number", "year", "pubmed_id"), limit)


# =================================================================== UniBind
@mcp.tool()
def unibind_search_tfbs(tf: str, limit: int = 20) -> str:
    """Search UniBind TFBS datasets by transcription factor (or keyword).

    Args:
        tf: TF name or keyword (e.g. "CTCF").
        limit: max datasets (default 20).
    """
    j = _get(f"{UNIBIND}/datasets/", format="json", search=tf, page_size=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", [])
    if not res:
        return f"No UniBind datasets for '{tf}'."
    rows = [f"# {j.get('count','?')} datasets", "dataset_id\ttf_name\ttotal_peaks"]
    for d in res:
        ds_id = (d.get("url", "") or "").rstrip("/").split("/")[-1]
        rows.append(f"{ds_id}\t{d.get('tf_name','')}\t{d.get('total_peaks','')}")
    return _cap(rows, "datasets")


@mcp.tool()
def unibind_get_dataset(dataset_id: str) -> str:
    """Get a UniBind TFBS dataset's metadata.

    Args:
        dataset_id: UniBind dataset id (e.g. "EXP059548.KC167_developmental_stage_6-12h_embryo.ABD-A").
    """
    d = _get(f"{UNIBIND}/datasets/{dataset_id}/", format="json")
    keys = [k for k in ("tf_name", "total_peaks", "cell_line", "biological_condition", "species", "url") if k in d]
    return "\n".join(f"{k}: {d.get(k)}" for k in keys) if keys else f"Dataset {dataset_id}: {str(d)[:400]}"


@mcp.tool()
def unibind_tfbs_in_region(chromosome: str, start: int, end: int, genome: str = "hg38") -> str:
    """TF binding sites overlapping a genomic region.

    NOTE: UniBind exposes no public per-region JSON API (region tracks are BED downloads
    served via the genome browser), so this returns pointers rather than a live region query.

    Args:
        chromosome, start, end: region (e.g. chr17 / 7668402 / 7687550).
        genome: assembly (default hg38).
    """
    return (f"region: {chromosome}:{start}-{end} ({genome})\n"
            f"UniBind has no public per-region JSON API. Download the robust TFBS BED tracks and "
            f"intersect locally: https://unibind.uio.no/downloads/ — or browse the region in the "
            f"UniBind genome-browser tracks. Use unibind_search_tfbs to find TF datasets to intersect.")


if __name__ == "__main__":
    mcp.run()
