#!/usr/bin/env python3
"""Variants MCP server — human genetic variants over PUBLIC APIs, no auth:

  * gnomAD (gnomad.broadinstitute.org/api) — population frequencies & constraint (r4, GraphQL)
  * ClinVar (NCBI E-utilities)             — clinical variant records
  * dbSNP (NCBI E-utilities)               — reference SNP (rsID) records

NOTE: the gnomAD API is 403-blocked from some networks (incl. this build sandbox); the
gnomAD tools follow the official GraphQL schema and work where the API is reachable, and
degrade gracefully otherwise. ClinVar/dbSNP (NCBI) are verified.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import time

import requests
from mcp.server.fastmcp import FastMCP

GNOMAD = "https://gnomad.broadinstitute.org/api"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HDRS = {"User-Agent": "Autogenesis-variants/1.0", "Accept": "application/json"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("variants")


def _gql(query: str, variables: dict):
    try:
        r = requests.post(GNOMAD, json={"query": query, "variables": variables},
                          headers={**HDRS, "Content-Type": "application/json"}, timeout=TIMEOUT)
        if r.status_code >= 400 or not r.headers.get("content-type", "").startswith("application/json"):
            raise RuntimeError(f"status {r.status_code}")
        j = r.json()
        if j.get("errors"):
            raise RuntimeError(j["errors"][0].get("message", "gnomAD error"))
        return j["data"]
    except Exception as e:
        raise RuntimeError(f"gnomAD API unavailable ({e}). It is 403-blocked from some networks "
                           f"(including this build sandbox); this tool works where gnomAD is reachable.")


def _eutils(endpoint, **params):
    # NCBI E-utilities rate-limit to ~3 req/s (429) without an API key; retry once on 429.
    for attempt in range(2):
        r = requests.get(f"{EUTILS}/{endpoint}", params={**params, "retmode": "json"}, headers=HDRS, timeout=TIMEOUT)
        if r.status_code == 429 and attempt == 0:
            time.sleep(1.0)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"NCBI {endpoint} -> {r.status_code}")
        return r.json()
    raise RuntimeError(f"NCBI {endpoint} rate-limited (429)")


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


# ===================================================================== gnomAD
@mcp.tool()
def get_variant(variant_id: str, dataset: str = "gnomad_r4") -> str:
    """Get a gnomAD variant's population frequencies (genome & exome).

    Args:
        variant_id: e.g. "1-55039974-G-T" (chrom-pos-ref-alt, GRCh38).
        dataset: gnomAD dataset (default "gnomad_r4").
    """
    q = ("query($v:String!,$d:DatasetId!){ variant(variantId:$v,dataset:$d){ variantId rsids "
         "genome{ac an af} exome{ac an af} } }")
    v = _gql(q, {"v": variant_id, "d": dataset}).get("variant")
    if not v:
        return f"No gnomAD variant {variant_id}."
    g, e = v.get("genome") or {}, v.get("exome") or {}
    return (f"variant: {v.get('variantId')}\nrsids: {', '.join(v.get('rsids') or [])}\n"
            f"genome_af: {g.get('af')} (ac={g.get('ac')}, an={g.get('an')})\n"
            f"exome_af: {e.get('af')} (ac={e.get('ac')}, an={e.get('an')})")


@mcp.tool()
def gene_variants(gene: str, limit: int = 25, dataset: str = "gnomad_r4") -> str:
    """List gnomAD variants in a gene (by symbol), highest allele frequency first.

    Args:
        gene: gene symbol (e.g. "PCSK9").
        limit: max variants (default 25).
        dataset: gnomAD dataset (default "gnomad_r4").
    """
    q = ("query($g:String!,$d:DatasetId!){ gene(gene_symbol:$g,reference_genome:GRCh38){ "
         "variants(dataset:$d){ variantId consequence hgvsp genome{af} exome{af} } } }")
    variants = (_gql(q, {"g": gene, "d": dataset}).get("gene") or {}).get("variants", [])
    if not variants:
        return f"No gnomAD variants for gene {gene}."
    def af(v):
        return max((v.get("genome") or {}).get("af") or 0, (v.get("exome") or {}).get("af") or 0)
    variants.sort(key=af, reverse=True)
    rows = [f"# {len(variants)} variants in {gene}", "variantId\tconsequence\thgvsp\tmax_af"]
    for v in variants[:max(1, limit)]:
        rows.append(f"{v.get('variantId','')}\t{v.get('consequence','')}\t{v.get('hgvsp','')}\t{af(v):.2e}")
    return _cap(rows, "variants")


@mcp.tool()
def search_variants(gene: str, limit: int = 25) -> str:
    """Search gnomAD variants within a gene (alias of gene_variants by symbol).

    Args:
        gene: gene symbol (e.g. "BRCA1").
        limit: max variants (default 25).
    """
    return gene_variants(gene, limit=limit)


@mcp.tool()
def gene_constraint(gene: str) -> str:
    """Get gnomAD loss-of-function / missense constraint metrics for a gene.

    Args:
        gene: gene symbol (e.g. "PCSK9").
    """
    q = ("query($g:String!){ gene(gene_symbol:$g,reference_genome:GRCh38){ gnomad_constraint{ "
         "pLI oe_lof oe_lof_lower oe_lof_upper oe_mis mis_z lof_z syn_z } } }")
    c = (_gql(q, {"g": gene}).get("gene") or {}).get("gnomad_constraint")
    if not c:
        return f"No gnomAD constraint data for {gene}."
    return (f"gene: {gene}\npLI: {c.get('pLI')}\noe_lof: {c.get('oe_lof')} "
            f"[{c.get('oe_lof_lower')}-{c.get('oe_lof_upper')}]\noe_mis: {c.get('oe_mis')}\n"
            f"mis_z: {c.get('mis_z')}\nlof_z: {c.get('lof_z')}\nsyn_z: {c.get('syn_z')}")


@mcp.tool()
def region_variants(chrom: str, start: int, stop: int, limit: int = 25, dataset: str = "gnomad_r4") -> str:
    """List gnomAD variants in a genomic region.

    Args:
        chrom: chromosome (e.g. "1"). start, stop: 1-based coordinates (GRCh38).
        limit: max variants (default 25). dataset: default "gnomad_r4".
    """
    q = ("query($c:String!,$s:Int!,$e:Int!,$d:DatasetId!){ region(chrom:$c,start:$s,stop:$e,"
         "reference_genome:GRCh38){ variants(dataset:$d){ variantId consequence genome{af} } } }")
    variants = (_gql(q, {"c": chrom, "s": start, "e": stop, "d": dataset}).get("region") or {}).get("variants", [])
    if not variants:
        return f"No gnomAD variants in {chrom}:{start}-{stop}."
    rows = [f"# {len(variants)} variants in {chrom}:{start}-{stop}", "variantId\tconsequence\taf"]
    for v in variants[:max(1, limit)]:
        rows.append(f"{v.get('variantId','')}\t{v.get('consequence','')}\t{(v.get('genome') or {}).get('af','')}")
    return _cap(rows, "variants")


@mcp.tool()
def liftover_variant(variant_id: str, source_genome: str = "GRCh38") -> str:
    """Lift a variant over between GRCh37 and GRCh38 via gnomAD.

    Args:
        variant_id: chrom-pos-ref-alt in the source assembly.
        source_genome: "GRCh38" or "GRCh37" (default GRCh38).
    """
    q = ("query($v:String!,$g:ReferenceGenomeId!){ liftover(source_variant_id:$v,reference_genome:$g){ "
         "liftover{ variantId reference_genome } } }")
    res = _gql(q, {"v": variant_id, "g": source_genome}).get("liftover", [])
    if not res:
        return f"No liftover for {variant_id}."
    rows = ["target_variantId\ttarget_genome"]
    for r in res:
        lo = r.get("liftover", {})
        rows.append(f"{lo.get('variantId','')}\t{lo.get('reference_genome','')}")
    return "\n".join(rows)


@mcp.tool()
def structural_variants(gene: str, limit: int = 25) -> str:
    """List gnomAD structural variants (SVs) overlapping a gene.

    Args:
        gene: gene symbol (e.g. "COL1A1").
        limit: max SVs (default 25).
    """
    q = ("query($g:String!){ gene(gene_symbol:$g,reference_genome:GRCh38){ "
         "structural_variants(dataset:gnomad_sv_r4){ variant_id type ac an af consequence } } }")
    svs = (_gql(q, {"g": gene}).get("gene") or {}).get("structural_variants", [])
    if not svs:
        return f"No gnomAD structural variants for {gene}."
    rows = [f"# {len(svs)} SVs in {gene}", "variant_id\ttype\taf\tconsequence"]
    for s in svs[:max(1, limit)]:
        rows.append(f"{s.get('variant_id','')}\t{s.get('type','')}\t{s.get('af','')}\t{s.get('consequence','')}")
    return _cap(rows, "SVs")


@mcp.tool()
def get_structural_variant(sv_id: str) -> str:
    """Get a gnomAD structural variant by id.

    Args:
        sv_id: structural variant id (e.g. "DEL_1_12345").
    """
    q = ("query($v:String!){ structural_variant(variantId:$v,dataset:gnomad_sv_r4){ "
         "variant_id type chrom pos end length ac an af } }")
    s = _gql(q, {"v": sv_id}).get("structural_variant")
    if not s:
        return f"No gnomAD structural variant {sv_id}."
    return (f"variant_id: {s.get('variant_id')}\ntype: {s.get('type')}\n"
            f"location: {s.get('chrom')}:{s.get('pos')}-{s.get('end')}\nlength: {s.get('length')}\n"
            f"af: {s.get('af')} (ac={s.get('ac')}, an={s.get('an')})")


@mcp.tool()
def mitochondrial_variants(gene: str, limit: int = 25) -> str:
    """List gnomAD mitochondrial variants in a gene.

    Args:
        gene: mitochondrial gene symbol (e.g. "MT-ND1").
        limit: max variants (default 25).
    """
    q = ("query($g:String!){ gene(gene_symbol:$g,reference_genome:GRCh38){ "
         "mitochondrial_variants(dataset:gnomad_r4){ variant_id ref alt an ac_hom ac_het } } }")
    mvs = (_gql(q, {"g": gene}).get("gene") or {}).get("mitochondrial_variants", [])
    if not mvs:
        return f"No gnomAD mitochondrial variants for {gene}."
    rows = [f"# {len(mvs)} mito variants in {gene}", "variant_id\tref>alt\tan\tac_hom\tac_het"]
    for m in mvs[:max(1, limit)]:
        rows.append(f"{m.get('variant_id','')}\t{m.get('ref','')}>{m.get('alt','')}\t{m.get('an','')}\t{m.get('ac_hom','')}\t{m.get('ac_het','')}")
    return _cap(rows, "variants")


# ==================================================================== ClinVar
def _clinvar_summaries(ids):
    if not ids:
        return []
    res = _eutils("esummary.fcgi", db="clinvar", id=",".join(ids)).get("result", {})
    out = []
    for uid in res.get("uids", []):
        d = res.get(uid, {})
        gc = d.get("germline_classification", {})
        sig = gc.get("description", "") if isinstance(gc, dict) else gc
        out.append(f"{uid}\t{(d.get('title') or '')[:55]}\t{sig}\t{d.get('accession','')}")
    return out


@mcp.tool()
def clinvar_variants(gene: str, limit: int = 20) -> str:
    """List ClinVar variant records for a gene.

    Args:
        gene: gene symbol (e.g. "BRCA1").
        limit: max records (default 20).
    """
    ids = _eutils("esearch.fcgi", db="clinvar", term=f"{gene}[gene]",
                  retmax=max(1, min(limit, MAX_ROWS))).get("esearchresult", {}).get("idlist", [])
    rows = _clinvar_summaries(ids)
    if not rows:
        return f"No ClinVar records for {gene}."
    return _cap(["uid\ttitle\tsignificance\taccession"] + rows, "records")


@mcp.tool()
def clinvar_search(query: str, limit: int = 20) -> str:
    """Search ClinVar by free-text query.

    Args:
        query: search term (e.g. "BRCA1 pathogenic", "Lynch syndrome").
        limit: max records (default 20).
    """
    ids = _eutils("esearch.fcgi", db="clinvar", term=query,
                  retmax=max(1, min(limit, MAX_ROWS))).get("esearchresult", {}).get("idlist", [])
    rows = _clinvar_summaries(ids)
    if not rows:
        return f"No ClinVar records for '{query}'."
    return _cap(["uid\ttitle\tsignificance\taccession"] + rows, "records")


@mcp.tool()
def clinvar_get_records(clinvar_ids: str) -> str:
    """Get specific ClinVar records by id.

    Args:
        clinvar_ids: comma-separated ClinVar UIDs (e.g. "4856951,446748").
    """
    ids = [i.strip() for i in clinvar_ids.split(",") if i.strip()]
    rows = _clinvar_summaries(ids)
    if not rows:
        return "No ClinVar records."
    return "\n".join(["uid\ttitle\tsignificance\taccession"] + rows)


@mcp.tool()
def clinvar_variant_by_rsid(rsid: str) -> str:
    """Find ClinVar records for a dbSNP rsID.

    Args:
        rsid: dbSNP rsID (e.g. "rs334" or "334").
    """
    rs = rsid if rsid.lower().startswith("rs") else f"rs{rsid}"
    ids = _eutils("esearch.fcgi", db="clinvar", term=rs, retmax=20).get("esearchresult", {}).get("idlist", [])
    rows = _clinvar_summaries(ids)
    if not rows:
        return f"No ClinVar records for {rs}."
    return _cap([f"# ClinVar records for {rs}", "uid\ttitle\tsignificance\taccession"] + rows, "records")


# ====================================================================== dbSNP
@mcp.tool()
def dbsnp_get_rsids(rsids: str) -> str:
    """Get dbSNP records for one or more rsIDs (alleles, MAF, clinical significance, genes).

    Args:
        rsids: comma-separated rsIDs (e.g. "rs334,rs7412").
    """
    ids = [i.strip().lower().replace("rs", "") for i in rsids.split(",") if i.strip()]
    if not ids:
        return "Provide one or more rsIDs."
    res = _eutils("esummary.fcgi", db="snp", id=",".join(ids)).get("result", {})
    rows = ["rsid\tgenes\tclinical_sig\tglobal_MAF"]
    for uid in res.get("uids", []):
        d = res.get(uid, {})
        genes = ", ".join(g.get("name", "") for g in (d.get("genes") or []) if isinstance(g, dict))
        mafs = d.get("global_mafs") or []
        maf = mafs[0].get("freq", "") if mafs and isinstance(mafs[0], dict) else ""
        rows.append(f"rs{d.get('snp_id', uid)}\t{genes}\t{d.get('clinical_significance','')}\t{maf}")
    return _cap(rows, "rsids") if len(rows) > 1 else "No dbSNP records."


@mcp.tool()
def dbsnp_search_by_region(chrom: str, start: int, end: int, limit: int = 25) -> str:
    """Find dbSNP rsIDs in a genomic region (GRCh38).

    Args:
        chrom: chromosome number (e.g. "11").
        start, end: base positions.
        limit: max rsIDs (default 25).
    """
    es = _eutils("esearch.fcgi", db="snp", term=f"{chrom}[CHR] AND {start}:{end}[CHRPOS]",
                 retmax=max(1, min(limit, MAX_ROWS)))
    ids = es.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return f"No dbSNP variants in {chrom}:{start}-{end}."
    total = es.get("esearchresult", {}).get("count", len(ids))
    res = _eutils("esummary.fcgi", db="snp", id=",".join(ids)).get("result", {})
    rows = [f"# {total} SNPs in {chrom}:{start}-{end}; showing {len(ids)}", "rsid\tgenes\tclinical_sig"]
    for uid in res.get("uids", []):
        d = res.get(uid, {})
        genes = ", ".join(g.get("name", "") for g in (d.get("genes") or []) if isinstance(g, dict))
        rows.append(f"rs{d.get('snp_id', uid)}\t{genes}\t{d.get('clinical_significance','')}")
    return _cap(rows, "rsids")


if __name__ == "__main__":
    mcp.run()
