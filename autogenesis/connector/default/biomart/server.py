#!/usr/bin/env python3
"""BioMart MCP server — a thin, self-contained wrapper over the PUBLIC Ensembl
BioMart REST API (https://www.ensembl.org/biomart/martservice).

Exposes genomic annotation, identifier translation, and cross-reference queries as
MCP tools. No authentication, no proprietary endpoints — just the public martservice.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

# Ensembl BioMart mirrors, tried in order. The main www host frequently rate-limits
# data queries (returns a "Service unavailable" HTML page); the regional mirrors are
# far more reliable, so useast is tried first.
MART_HOSTS = [
    "https://useast.ensembl.org/biomart/martservice",
    "https://www.ensembl.org/biomart/martservice",
    "https://uswest.ensembl.org/biomart/martservice",
    "https://asia.ensembl.org/biomart/martservice",
]
GENE_MART = "ENSEMBL_MART_ENSEMBL"
DEFAULT_DATASET = "hsapiens_gene_ensembl"
TIMEOUT = 60
MAX_ROWS = 500  # cap TSV rows returned to the agent to keep responses bounded

mcp = FastMCP("biomart")


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _get(params: dict) -> str:
    """GET martservice with params, trying mirrors in order; return text or raise.

    Skips a mirror that errors, times out, or serves an HTML "Service unavailable"
    page (the main host does this under load); raises only if every mirror fails.
    """
    last = None
    for host in MART_HOSTS:
        try:
            r = requests.get(host, params=params, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as e:
            last = f"{host}: {e}"
            continue
        text = r.text
        head = text.lstrip()[:300].lower()
        if "<html" in head or "service unavailable" in head:
            last = f"{host}: service unavailable"
            continue
        if text.lstrip().startswith("Query ERROR") or "Exception" in text[:200]:
            raise RuntimeError(f"BioMart returned an error:\n{text[:500]}")
        return text
    raise RuntimeError(f"All BioMart mirrors failed. Last error: {last}")


def _cap(rows: list[str], note_scope: str) -> str:
    """Join TSV rows, capping at MAX_ROWS with a note."""
    if len(rows) > MAX_ROWS:
        kept = rows[:MAX_ROWS]
        kept.append(f"... ({len(rows) - MAX_ROWS} more {note_scope} truncated; narrow your query)")
        return "\n".join(kept)
    return "\n".join(rows)


def _build_query_xml(dataset: str, attributes: list[str],
                     filters: Optional[dict] = None) -> str:
    """Build a BioMart Query XML (TSV, with header)."""
    q = ET.Element("Query", {
        "virtualSchemaName": "default", "formatter": "TSV", "header": "1",
        "uniqueRows": "1", "count": "0", "datasetConfigVersion": "0.6",
    })
    ds = ET.SubElement(q, "Dataset", {"name": dataset, "interface": "default"})
    for name, value in (filters or {}).items():
        ET.SubElement(ds, "Filter", {"name": name, "value": str(value)})
    for attr in attributes:
        ET.SubElement(ds, "Attribute", {"name": attr})
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE Query>\n' + ET.tostring(q, encoding="unicode")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_marts() -> str:
    """List the available BioMart marts (databases), e.g. ENSEMBL_MART_ENSEMBL.

    Use this first to discover which mart to query. Returns 'name<TAB>displayName'.
    """
    xml = _get({"type": "registry"})
    root = ET.fromstring(xml)
    rows = ["name\tdisplayName"]
    for m in root.findall(".//MartURLLocation"):
        rows.append(f"{m.get('name','')}\t{m.get('displayName','')}")
    return "\n".join(rows) if len(rows) > 1 else "No marts found."


@mcp.tool()
def list_datasets(mart: str = GENE_MART) -> str:
    """List datasets in a mart (e.g. hsapiens_gene_ensembl for human genes).

    Args:
        mart: Mart name from list_marts (default ENSEMBL_MART_ENSEMBL).
    Returns 'dataset<TAB>description' rows.
    """
    text = _get({"type": "datasets", "mart": mart})
    rows = ["dataset\tdescription"]
    for line in text.strip().splitlines():
        cols = line.split("\t")
        if len(cols) >= 3 and cols[0] == "TableSet":
            rows.append(f"{cols[1]}\t{cols[2]}")
    return _cap(rows, "datasets")


# A curated set of the most commonly used attributes for *_gene_ensembl datasets.
_COMMON_GENE_ATTRS = [
    ("ensembl_gene_id", "Ensembl gene ID"),
    ("ensembl_transcript_id", "Ensembl transcript ID"),
    ("external_gene_name", "Gene name (symbol)"),
    ("hgnc_symbol", "HGNC symbol (human)"),
    ("entrezgene_id", "NCBI (Entrez) gene ID"),
    ("uniprotswissprot", "UniProt/SwissProt accession"),
    ("chromosome_name", "Chromosome/scaffold"),
    ("start_position", "Gene start (bp)"),
    ("end_position", "Gene end (bp)"),
    ("strand", "Strand"),
    ("gene_biotype", "Gene biotype"),
    ("description", "Gene description"),
]


@mcp.tool()
def list_common_attributes(dataset: str = DEFAULT_DATASET) -> str:
    """List the most commonly used attributes (fields) for a gene dataset.

    A curated shortlist for the frequent case; use list_all_attributes to search
    the full attribute set.

    Args:
        dataset: e.g. hsapiens_gene_ensembl.
    """
    valid = {ln.split("\t")[0] for ln in _get(
        {"type": "attributes", "dataset": dataset}).strip().splitlines() if ln}
    rows = ["attribute\tdescription"]
    for name, desc in _COMMON_GENE_ATTRS:
        if name in valid:
            rows.append(f"{name}\t{desc}")
    return "\n".join(rows)


@mcp.tool()
def list_all_attributes(dataset: str = DEFAULT_DATASET, search: str = "") -> str:
    """List all attributes for a dataset, optionally filtered by a search substring.

    The full list can be thousands of entries — pass `search` (matched against the
    attribute name and description) to narrow it.

    Args:
        dataset: e.g. hsapiens_gene_ensembl.
        search: case-insensitive substring filter (optional).
    """
    text = _get({"type": "attributes", "dataset": dataset})
    s = search.lower().strip()
    rows = ["attribute\tdescription"]
    for line in text.strip().splitlines():
        cols = line.split("\t")
        name = cols[0] if cols else ""
        desc = cols[1] if len(cols) > 1 else ""
        if not name:
            continue
        if s and s not in name.lower() and s not in desc.lower():
            continue
        rows.append(f"{name}\t{desc}")
    return _cap(rows, "attributes")


@mcp.tool()
def list_filters(dataset: str = DEFAULT_DATASET, search: str = "") -> str:
    """List the filters available to constrain a query on a dataset.

    Args:
        dataset: e.g. hsapiens_gene_ensembl.
        search: case-insensitive substring filter (optional).
    """
    text = _get({"type": "filters", "dataset": dataset})
    s = search.lower().strip()
    rows = ["filter\tdescription"]
    for line in text.strip().splitlines():
        cols = line.split("\t")
        name = cols[0] if cols else ""
        desc = cols[1] if len(cols) > 1 else ""
        if not name:
            continue
        if s and s not in name.lower() and s not in desc.lower():
            continue
        rows.append(f"{name}\t{desc}")
    return _cap(rows, "filters")


@mcp.tool()
def get_data(dataset: str, attributes: list[str],
             filters: Optional[dict] = None) -> str:
    """Run a BioMart query: fetch `attributes` from `dataset`, constrained by `filters`.

    This is the main data-retrieval tool. Returns TSV with a header row.

    Args:
        dataset: e.g. hsapiens_gene_ensembl (see list_datasets).
        attributes: attribute names to return, e.g. ["ensembl_gene_id", "hgnc_symbol"].
        filters: optional {filter_name: value}; value may be comma-separated for lists,
            e.g. {"hgnc_symbol": "TP53,BRCA1"} or {"chromosome_name": "17"}.
    """
    if not attributes:
        return "Error: `attributes` must be a non-empty list (see list_common_attributes)."
    xml = _build_query_xml(dataset, attributes, filters)
    text = _get({"query": xml})
    rows = [ln for ln in text.strip().splitlines()]
    return _cap(rows, "rows") if rows else "No rows returned."


@mcp.tool()
def get_translation(dataset: str, from_attribute: str, to_attribute: str,
                    value: str) -> str:
    """Translate a single identifier from one attribute type to another.

    Args:
        dataset: e.g. hsapiens_gene_ensembl.
        from_attribute: source ID type, usable as both filter and attribute
            (e.g. "hgnc_symbol", "ensembl_gene_id", "entrezgene_id").
        to_attribute: target ID type (e.g. "ensembl_gene_id").
        value: the identifier to translate (e.g. "TP53").
    """
    return get_data(dataset, [from_attribute, to_attribute], {from_attribute: value})


@mcp.tool()
def batch_translate(dataset: str, from_attribute: str, to_attribute: str,
                    values: list[str]) -> str:
    """Translate many identifiers at once between two attribute types.

    Args:
        dataset: e.g. hsapiens_gene_ensembl.
        from_attribute: source ID type (e.g. "hgnc_symbol").
        to_attribute: target ID type (e.g. "entrezgene_id").
        values: list of identifiers, e.g. ["TP53", "BRCA1", "EGFR"].
    """
    if not values:
        return "Error: `values` must be a non-empty list."
    joined = ",".join(str(v) for v in values)
    return get_data(dataset, [from_attribute, to_attribute], {from_attribute: joined})


if __name__ == "__main__":
    mcp.run()
