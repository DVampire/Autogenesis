#!/usr/bin/env python3
"""Expression MCP server — gene expression over the PUBLIC GTEx Portal API
(https://gtexportal.org/api/v2), no auth. GTEx tissue expression and eQTLs, pinned
to the gtex_v10 dataset (GENCODE v39 identifiers).

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import statistics
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

BASE = "https://gtexportal.org/api/v2"
DATASET = "gtex_v10"
GENCODE = "v39"                 # GENCODE release matching gtex_v10 gencodeIds
HDRS = {"User-Agent": "Autogenesis-gtex/1.0", "Accept": "application/json"}
TIMEOUT = 45
MAX_ROWS = 60

mcp = FastMCP("expression")


def _get(path: str, **params) -> list:
    r = requests.get(f"{BASE}{path}", params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GTEx {path} -> {r.status_code}: {r.text[:200]}")
    j = r.json()
    if isinstance(j, list):
        return j
    return j.get("data", []) if isinstance(j, dict) else []


def _get_raw(path: str, **params) -> dict:
    """GET returning the full JSON object (for endpoints that are not paginated lists)."""
    r = requests.get(f"{BASE}{path}", params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GTEx {path} -> {r.status_code}: {r.text[:200]}")
    return r.json() or {}


def _paging_total(path: str, **params) -> Optional[int]:
    r = requests.get(f"{BASE}{path}", params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        return None
    info = (r.json() or {}).get("paging_info", {})
    return info.get("totalNumberOfItems")


def _resolve_gene(gene: str) -> tuple[str, str]:
    """Resolve a symbol/gencodeId to (gencodeId, geneSymbol) in the pinned GENCODE version."""
    if gene.upper().startswith("ENSG"):
        return gene, gene
    data = _get("/reference/gene", geneId=gene, gencodeVersion=GENCODE, genomeBuild="GRCh38/hg38")
    if not data:
        raise RuntimeError(f"No GTEx gene for '{gene}'.")
    return data[0]["gencodeId"], data[0].get("geneSymbol", gene)


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
@mcp.tool()
def gtex_tissue_sites() -> str:
    """List GTEx tissue sites (their ids and display names). Use ids for other tools."""
    data = _get("/dataset/tissueSiteDetail", itemsPerPage=100, datasetId=DATASET)
    rows = ["tissueSiteDetailId\ttissue\tsamples(RNASeq)"]
    for d in data:
        rows.append(f"{d.get('tissueSiteDetailId','')}\t{d.get('tissueSiteDetail','')}\t{d.get('rnaSeqSampleCount','')}")
    return _cap(rows, "tissues")


@mcp.tool()
def gtex_dataset_info() -> str:
    """Describe the available GTEx datasets (id, samples, subjects, GENCODE version)."""
    data = _get("/metadata/dataset")
    rows = ["datasetId\tsamples\tsubjects\tgencode"]
    for d in data:
        rows.append(f"{d.get('datasetId','')}\t{d.get('rnaSeqSampleCount', d.get('sampleCount',''))}\t"
                    f"{d.get('subjectCount','')}\t{d.get('gencodeVersion','')}")
    return "\n".join(rows)


@mcp.tool()
def gtex_sample_info(tissue: str = "", limit: int = 10) -> str:
    """Sample metadata for the dataset, optionally filtered by tissue.

    Args:
        tissue: tissueSiteDetailId (e.g. "Liver"); empty for all.
        limit: max sample rows to show (default 10).
    """
    params = {"datasetId": DATASET, "itemsPerPage": max(1, min(limit, MAX_ROWS))}
    if tissue.strip():
        params["tissueSiteDetailId"] = tissue.strip()
    total = _paging_total("/dataset/sample", **params)
    data = _get("/dataset/sample", **params)
    rows = [f"# samples{f' in {tissue}' if tissue else ''}: {total if total is not None else len(data)}",
            "aliquotId\ttissue\tdataType\tischemicTime"]
    for d in data:
        rows.append(f"{d.get('aliquotId','')}\t{d.get('tissueSiteDetail','')}\t{d.get('dataType','')}\t{d.get('ischemicTime','')}")
    return _cap(rows, "samples")


@mcp.tool()
def gtex_resolve_genes(gene: str) -> str:
    """Resolve a gene symbol to its GTEx gencodeId (and basic annotation).

    Args:
        gene: gene symbol (e.g. "TP53") or Ensembl id.
    """
    data = _get("/reference/gene", geneId=gene, gencodeVersion=GENCODE, genomeBuild="GRCh38/hg38")
    if not data:
        return f"No GTEx gene for '{gene}'."
    rows = ["geneSymbol\tgencodeId\tchromosome\tgeneType"]
    for d in data:
        rows.append(f"{d.get('geneSymbol','')}\t{d.get('gencodeId','')}\t{d.get('chromosome','')}\t{d.get('geneType','')}")
    return _cap(rows, "genes")


@mcp.tool()
def gtex_median_expression(gene: str) -> str:
    """Median expression (TPM) of a gene across all GTEx tissues, highest first.

    Args:
        gene: gene symbol or gencodeId (e.g. "TP53").
    """
    gid, sym = _resolve_gene(gene)
    data = _get("/expression/medianGeneExpression", gencodeId=gid, datasetId=DATASET, itemsPerPage=100)
    if not data:
        return f"No expression data for {gene} ({gid})."
    data.sort(key=lambda d: d.get("median", 0), reverse=True)
    rows = [f"# {sym} ({gid}) — median TPM by tissue", "tissue\tmedian_TPM"]
    for d in data:
        rows.append(f"{d.get('tissueSiteDetailId','')}\t{d.get('median','')}")
    return _cap(rows, "tissues")


@mcp.tool()
def gtex_expression_summary(gene: str, top: int = 8) -> str:
    """Concise expression summary for a gene: highest- and lowest-expressing tissues.

    Args:
        gene: gene symbol or gencodeId.
        top: how many top/bottom tissues to show (default 8).
    """
    gid, sym = _resolve_gene(gene)
    data = _get("/expression/medianGeneExpression", gencodeId=gid, datasetId=DATASET, itemsPerPage=100)
    if not data:
        return f"No expression data for {gene} ({gid})."
    vals = sorted(((d.get("median", 0), d.get("tissueSiteDetailId", "")) for d in data), reverse=True)
    med_all = statistics.median([v for v, _ in vals])
    out = [f"# {sym} ({gid}) expression summary (TPM, {DATASET})",
           f"tissues: {len(vals)} | median-of-medians: {med_all:.2f} | max: {vals[0][0]} ({vals[0][1]})",
           "\nhighest:"]
    out += [f"  {t}: {v}" for v, t in vals[:max(1, top)]]
    out.append("lowest:")
    out += [f"  {t}: {v}" for v, t in vals[-max(1, top):]]
    return "\n".join(out)


@mcp.tool()
def gtex_gene_expression(gene: str, tissue: str) -> str:
    """Per-sample expression distribution of a gene in one tissue (summary stats).

    Args:
        gene: gene symbol or gencodeId.
        tissue: tissueSiteDetailId (e.g. "Liver").
    """
    gid, sym = _resolve_gene(gene)
    data = _get("/expression/geneExpression", gencodeId=gid, tissueSiteDetailId=tissue, datasetId=DATASET)
    if not data:
        return f"No expression data for {gene} in {tissue}."
    rec = data[0]
    vals = rec.get("data") or []
    unit = rec.get("unit", "TPM")
    if not vals:
        return f"No per-sample values for {gene} in {tissue}."
    vals_sorted = sorted(vals)
    return (f"# {sym} ({gid}) in {tissue} ({DATASET})\nsamples: {len(vals)}\nunit: {unit}\n"
            f"min: {vals_sorted[0]:.3f}\nmedian: {statistics.median(vals):.3f}\n"
            f"mean: {statistics.mean(vals):.3f}\nmax: {vals_sorted[-1]:.3f}")


@mcp.tool()
def gtex_top_expressed_genes(tissue: str, limit: int = 20) -> str:
    """Top-expressed genes in a tissue by median TPM.

    Args:
        tissue: tissueSiteDetailId (e.g. "Liver").
        limit: max genes (default 20).
    """
    data = _get("/expression/topExpressedGene", tissueSiteDetailId=tissue, datasetId=DATASET,
                itemsPerPage=max(1, min(limit, MAX_ROWS)))
    if not data:
        return f"No data for tissue '{tissue}'."
    rows = [f"# top expressed genes in {tissue}", "geneSymbol\tgencodeId\tmedian_TPM"]
    for d in data:
        rows.append(f"{d.get('geneSymbol','')}\t{d.get('gencodeId','')}\t{d.get('median','')}")
    return _cap(rows, "genes")


@mcp.tool()
def gtex_eqtl_genes(tissue: str, limit: int = 25) -> str:
    """List eGenes (genes with a significant cis-eQTL) in a tissue.

    Args:
        tissue: tissueSiteDetailId (e.g. "Whole_Blood").
        limit: max eGenes (default 25).
    """
    data = _get("/association/egene", tissueSiteDetailId=tissue, datasetId=DATASET,
                itemsPerPage=max(1, min(limit, MAX_ROWS)))
    if not data:
        return f"No eGenes for tissue '{tissue}'."
    rows = [f"# eGenes in {tissue}", "geneSymbol\tgencodeId\tempiricalPValue"]
    for d in data:
        rows.append(f"{d.get('geneSymbol','')}\t{d.get('gencodeId','')}\t{d.get('empiricalPValue','')}")
    return _cap(rows, "eGenes")


@mcp.tool()
def gtex_single_tissue_eqtls(gene: str, tissue: str, limit: int = 25) -> str:
    """Single-tissue cis-eQTLs for a gene in a tissue (variant, p-value, effect size).

    Args:
        gene: gene symbol or gencodeId.
        tissue: tissueSiteDetailId (e.g. "Whole_Blood").
        limit: max eQTLs (default 25).
    """
    gid, sym = _resolve_gene(gene)
    data = _get("/association/singleTissueEqtl", gencodeId=gid, tissueSiteDetailId=tissue,
                datasetId=DATASET, itemsPerPage=max(1, min(limit, MAX_ROWS)))
    if not data:
        return f"No significant single-tissue eQTLs for {sym} in {tissue}."
    rows = [f"# {sym} ({gid}) eQTLs in {tissue}", "variantId\tsnpId\tpValue\tnes"]
    for d in data:
        rows.append(f"{d.get('variantId','')}\t{d.get('snpId','')}\t{d.get('pValue','')}\t{d.get('nes','')}")
    return _cap(rows, "eQTLs")


def _resolve_variant(variant: str) -> str:
    """Resolve a dbSNP rsID to a GTEx variantId; pass a variantId through unchanged."""
    if not variant.lower().startswith("rs"):
        return variant
    data = _get("/dataset/variant", snpId=variant, datasetId=DATASET)
    if not data:
        raise RuntimeError(f"No GTEx variant for rsID '{variant}'.")
    return data[0]["variantId"]


@mcp.tool()
def gtex_multi_tissue_eqtls(gene: str, limit: int = 40) -> str:
    """Multi-tissue eQTL meta-analysis for a gene.

    Attempts GTEx's Metasoft cross-tissue meta-analysis (per-tissue m-value/p-value).
    Metasoft is not populated for every gene in the v2 API, so when it is empty this
    falls back to aggregating the gene's significant single-tissue cis-eQTLs across all
    tissues, grouped per variant: how many tissues each lead variant is significant in,
    its best p-value, and its effect-size range — a practical multi-tissue summary.

    Args:
        gene: gene symbol or gencodeId (e.g. "ERAP2").
        limit: max variants/rows to return (default 40).
    """
    gid, sym = _resolve_gene(gene)
    cap = max(1, min(limit, MAX_ROWS))
    meta = _get("/association/metasoft", gencodeId=gid, datasetId=DATASET, itemsPerPage=cap)
    if meta:
        rows = [f"# {sym} ({gid}) — multi-tissue eQTL meta-analysis (Metasoft, {DATASET})",
                "variantId\ttissue\tmValue(posterior)\tpValue\tnes"]
        for d in meta:
            rows.append(f"{d.get('variantId','')}\t{d.get('tissueSiteDetailId','')}\t"
                        f"{d.get('mValue','')}\t{d.get('pValue','')}\t{d.get('nes','')}")
        return _cap(rows, "associations")

    # Fallback: aggregate significant single-tissue eQTLs across tissues.
    assoc = _get("/association/singleTissueEqtl", gencodeId=gid, datasetId=DATASET, itemsPerPage=1000)
    if not assoc:
        return f"No multi-tissue eQTL results for {sym} ({gid})."
    by_variant: dict[str, dict] = {}
    for a in assoc:
        vid = a.get("variantId", "")
        p = a.get("pValue")
        nes = a.get("nes")
        rec = by_variant.setdefault(vid, {"snpId": a.get("snpId", ""), "tissues": set(),
                                          "best_p": None, "nes": []})
        rec["tissues"].add(a.get("tissueSiteDetailId", ""))
        if isinstance(p, (int, float)) and (rec["best_p"] is None or p < rec["best_p"]):
            rec["best_p"] = p
        if isinstance(nes, (int, float)):
            rec["nes"].append(nes)
    ranked = sorted(by_variant.items(), key=lambda kv: len(kv[1]["tissues"]), reverse=True)
    rows = [f"# {sym} ({gid}) — multi-tissue eQTL summary across tissues ({DATASET}); "
            f"Metasoft empty, aggregated from {len(assoc)} single-tissue eQTLs over "
            f"{len({a.get('tissueSiteDetailId') for a in assoc})} tissues",
            "variantId\tsnpId\tn_tissues\tbest_pValue\tnes_min..max"]
    for vid, rec in ranked[:cap]:
        nes = rec["nes"]
        nes_rng = f"{min(nes):.3f}..{max(nes):.3f}" if nes else ""
        rows.append(f"{vid}\t{rec['snpId']}\t{len(rec['tissues'])}\t{rec['best_p']}\t{nes_rng}")
    return _cap(rows, "variants")


@mcp.tool()
def gtex_calculate_eqtl(gene: str, variant: str, tissue: str) -> str:
    """Compute a single-tissue cis-eQTL for an arbitrary gene-variant pair on the fly.

    Runs GTEx's dynamic eQTL calculation (dyneqtl): regresses the gene's expression
    on the variant's genotype in one tissue and returns the association statistics,
    even for pairs not in the pre-computed significant-eQTL tables.

    Args:
        gene: gene symbol or gencodeId (e.g. "TP53").
        variant: GTEx variantId (e.g. "chr17_7676154_G_C_b38") or dbSNP rsID (resolved automatically).
        tissue: tissueSiteDetailId (e.g. "Whole_Blood").
    """
    gid, sym = _resolve_gene(gene)
    vid = _resolve_variant(variant)
    res = _get_raw("/association/dyneqtl", gencodeId=gid, variantId=vid,
                   tissueSiteDetailId=tissue, datasetId=DATASET)
    if res.get("pValue") is None:
        return f"No eQTL result for {sym} / {variant} in {tissue}."
    n = len(res.get("genotypes") or res.get("data") or [])
    fields = ["variantId", "gencodeId", "geneSymbol", "tissueSiteDetailId", "pValue",
              "nes", "tStatistic", "maf", "homoRefCount", "hetCount", "homoAltCount",
              "pValueThreshold"]
    out = [f"# on-the-fly eQTL: {sym} ({gid}) vs {vid} in {tissue} ({DATASET})",
           f"samples: {n}"]
    for f in fields:
        if res.get(f) is not None:
            out.append(f"{f}: {res[f]}")
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
