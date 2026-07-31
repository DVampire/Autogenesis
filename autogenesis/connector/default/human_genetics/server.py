#!/usr/bin/env python3
"""Human Genetics MCP server — human genetics associations over PUBLIC APIs, no auth:

  * GWAS Catalog (EMBL-EBI REST)   — variant/gene/trait associations, studies, traits
  * eQTL Catalogue (EMBL-EBI v2)   — expression QTL datasets and associations
  * FinnGen PheWeb (r12, public)   — gene-based PheWAS, phenotype catalogue
  * PheWAS (GWAS Catalog)          — phenome-wide associations for a variant

GWAS endpoint mappings referenced from the open-source koido/gwas-catalog-mcp
(Apache-2.0). Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

GWAS = "https://www.ebi.ac.uk/gwas/rest/api"
EQTL = "https://www.ebi.ac.uk/eqtl/api/v2"
FINNGEN = "https://r12.finngen.fi"          # versioned release host is publicly accessible
ENSEMBL = "https://rest.ensembl.org"
HDRS = {"User-Agent": "Mozilla/5.0 Autogenesis-humgen/1.0", "Accept": "application/json"}
TIMEOUT = 30
MAX_ROWS = 50

# PheWAS portals this connector knows about.
_PHEWAS_INSTANCES = [
    {"id": "finngen", "name": "FinnGen (Finnish biobank)", "release": "r12",
     "base": FINNGEN, "status": "public API (gene/phenotype)"},
    {"id": "bbj", "name": "BioBank Japan PheWeb", "release": "pheweb.jp",
     "base": "https://pheweb.jp", "status": "web portal; limited public API"},
]

mcp = FastMCP("human_genetics")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:150]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _pval(a: dict):
    if a.get("pvalue") is not None:
        return a["pvalue"]
    m, e = a.get("pvalueMantissa"), a.get("pvalueExponent")
    if m is not None and e is not None:
        return f"{m}e{e}"
    return ""


def _risk_allele(a: dict) -> str:
    for locus in a.get("loci", []) or []:
        for ra in locus.get("strongestRiskAlleles", []) or []:
            return ra.get("riskAlleleName", "")
    return ""


# ============================================================== GWAS Catalog
@mcp.tool()
def gwas_associations_for_variant(rsid: str, limit: int = 30) -> str:
    """GWAS Catalog associations for a variant (rsID) — its trait associations.

    Args:
        rsid: dbSNP rsID (e.g. "rs429358").
        limit: max associations (default 30).
    Returns 'pvalue<TAB>riskAllele<TAB>OR/beta<TAB>study' rows.
    """
    try:
        data = _get(f"{GWAS}/singleNucleotidePolymorphisms/{rsid}/associations", size=max(1, limit))
    except (RuntimeError, requests.RequestException):
        return (f"The GWAS Catalog associations endpoint for {rsid} did not respond in time "
                f"(it can be very slow for highly-associated variants). Try again, or use "
                f"gwas_get_variant / gwas_associations_for_gene.")
    assocs = data.get("_embedded", {}).get("associations", [])
    if not assocs:
        return f"No GWAS associations for {rsid}."
    rows = [f"# {rsid} — {len(assocs)} associations", "pvalue\triskAllele\tOR/beta\tstudy"]
    for a in assocs[:max(1, limit)]:
        eff = a.get("orPerCopyNum") or a.get("betaNum") or ""
        study = ((a.get("_links", {}).get("study", {}) or {}).get("href", "") or "").rstrip("/").split("/")[-1]
        rows.append(f"{_pval(a)}\t{_risk_allele(a)}\t{eff}\t{study}")
    return _cap(rows, "associations")


@mcp.tool()
def gwas_associations_for_gene(gene: str, limit: int = 30) -> str:
    """GWAS-cataloged variants mapped to a gene (their rsIDs, class, location).

    Args:
        gene: gene symbol (e.g. "APOE").
        limit: max variants (default 30).
    """
    data = _get(f"{GWAS}/singleNucleotidePolymorphisms/search/findByGene", geneName=gene, size=max(1, min(limit, MAX_ROWS)))
    snps = data.get("_embedded", {}).get("singleNucleotidePolymorphisms", [])
    if not snps:
        return f"No GWAS-cataloged variants for gene {gene}."
    seen, rows = set(), [f"# GWAS variants in {gene}", "rsId\tfunctionalClass\tlocation"]
    for s in snps:
        rsid = s.get("rsId", "")
        if rsid in seen:
            continue
        seen.add(rsid)
        locs = "; ".join(f"{l.get('chromosomeName','')}:{l.get('chromosomePosition','')}" for l in s.get("locations", []) or [])
        rows.append(f"{rsid}\t{s.get('functionalClass','')}\t{locs}")
    return _cap(rows, "variants")


def _resolve_efo(trait: str) -> tuple[str, str]:
    """Resolve a trait name to (efo_short_form, matched_trait_label)."""
    if trait.upper().startswith(("EFO_", "MONDO_", "HP_", "ORPHANET")):
        return trait, trait
    data = _get(f"{GWAS}/efoTraits/search/findByEfoTrait", trait=trait)
    ts = data.get("_embedded", {}).get("efoTraits", [])
    if not ts:
        raise RuntimeError(f"No EFO trait matching '{trait}'.")
    return ts[0].get("shortForm", ""), ts[0].get("trait", trait)


@mcp.tool()
def gwas_associations_for_trait(trait: str, limit: int = 30) -> str:
    """GWAS Catalog associations for a trait (by name or EFO id).

    Args:
        trait: trait name (e.g. "Alzheimer disease") or EFO id (e.g. "EFO_0000249").
        limit: max associations (default 30).
    """
    efo, label = _resolve_efo(trait)
    try:
        data = _get(f"{GWAS}/efoTraits/{efo}/associations", size=max(1, limit))
    except (RuntimeError, requests.RequestException):
        return (f"The GWAS Catalog associations endpoint for trait '{label}' ({efo}) did not respond "
                f"in time (it can be very slow for common traits). Try gwas_search_studies instead.")
    assocs = data.get("_embedded", {}).get("associations", [])
    if not assocs:
        return f"No GWAS associations for trait '{trait}' ({efo})."
    rows = [f"# {label} ({efo}) — {len(assocs)} associations", "pvalue\triskAllele\tOR/beta"]
    for a in assocs[:max(1, limit)]:
        rows.append(f"{_pval(a)}\t{_risk_allele(a)}\t{a.get('orPerCopyNum') or a.get('betaNum') or ''}")
    return _cap(rows, "associations")


@mcp.tool()
def gwas_search_traits(query: str) -> str:
    """Search GWAS Catalog EFO traits by name.

    Args:
        query: trait name (e.g. "Alzheimer disease").
    Returns 'trait<TAB>efo_id<TAB>uri' rows.
    """
    data = _get(f"{GWAS}/efoTraits/search/findByEfoTrait", trait=query)
    ts = data.get("_embedded", {}).get("efoTraits", [])
    if not ts:
        return f"No EFO traits matching '{query}'."
    rows = ["trait\tefo_id\turi"] + [f"{t.get('trait','')}\t{t.get('shortForm','')}\t{t.get('uri','')}" for t in ts]
    return _cap(rows, "traits")


@mcp.tool()
def gwas_search_studies(disease_trait: str, limit: int = 20) -> str:
    """Search GWAS Catalog studies by disease/trait. Falls back to EFO-trait studies.

    Args:
        disease_trait: reported disease/trait (e.g. "Alzheimer disease").
        limit: max studies (default 20).
    """
    data = _get(f"{GWAS}/studies/search/findByDiseaseTrait", diseaseTrait=disease_trait, size=max(1, min(limit, MAX_ROWS)))
    studies = data.get("_embedded", {}).get("studies", [])
    if not studies:
        try:
            efo, _ = _resolve_efo(disease_trait)
            studies = _get(f"{GWAS}/efoTraits/{efo}/studies").get("_embedded", {}).get("studies", [])
        except RuntimeError:
            studies = []
    if not studies:
        return f"No GWAS studies for '{disease_trait}'."
    rows = ["accession\ttrait\tpubmed\tsampleSize"]
    for s in studies[:max(1, limit)]:
        init = "; ".join(x.get("initialSampleSize", "") for x in [s]) if s.get("initialSampleSize") else ""
        rows.append(f"{s.get('accessionId','')}\t{s.get('diseaseTrait',{}).get('trait','') if isinstance(s.get('diseaseTrait'),dict) else ''}\t"
                    f"{s.get('publicationInfo',{}).get('pubmedId','')}\t{(s.get('initialSampleSize','') or '')[:40]}")
    return _cap(rows, "studies")


@mcp.tool()
def gwas_get_study(accession: str) -> str:
    """Get a GWAS Catalog study by accession id.

    Args:
        accession: study accession (e.g. "GCST002245").
    """
    s = _get(f"{GWAS}/studies/{accession}")
    pub = s.get("publicationInfo", {}) or {}
    dt = s.get("diseaseTrait", {}) or {}
    return (f"accession: {s.get('accessionId')}\ntrait: {dt.get('trait','')}\n"
            f"initialSampleSize: {s.get('initialSampleSize','')}\n"
            f"pubmedId: {pub.get('pubmedId','')}\ntitle: {pub.get('title','')}\n"
            f"author: {pub.get('author',{}).get('fullname','') if isinstance(pub.get('author'),dict) else ''}")


@mcp.tool()
def gwas_get_variant(rsid: str) -> str:
    """Get a GWAS Catalog variant (SNP) record by rsID.

    Args:
        rsid: dbSNP rsID (e.g. "rs429358").
    """
    s = _get(f"{GWAS}/singleNucleotidePolymorphisms/{rsid}")
    locs = "; ".join(f"{l.get('chromosomeName','')}:{l.get('chromosomePosition','')} ({l.get('region',{}).get('name','')})"
                     for l in s.get("locations", []) or [])
    genes = ", ".join(g.get("geneName", "") for g in s.get("genomicContexts", []) or [] if g.get("isClosestGene"))
    return (f"rsId: {s.get('rsId')}\nfunctionalClass: {s.get('functionalClass','')}\n"
            f"locations: {locs}\nnearest_genes: {genes}")


# ============================================================= eQTL Catalogue
@mcp.tool()
def eqtl_list_datasets(quant_method: str = "", tissue: str = "", limit: int = 30) -> str:
    """List eQTL Catalogue datasets, optionally filtered by quant method or tissue.

    Args:
        quant_method: e.g. "ge" (gene expression), "tx", "exon", "aptamer" (optional).
        tissue: substring to filter tissue label (optional).
        limit: max datasets (default 30).
    """
    data = _get(f"{EQTL}/datasets", size=1000)
    if not isinstance(data, list):
        return "No eQTL datasets."
    t = tissue.lower().strip()
    rows = ["dataset_id\tstudy\ttissue\tquant\tcondition"]
    for d in data:
        if quant_method and d.get("quant_method") != quant_method:
            continue
        if t and t not in (d.get("tissue_label", "") or "").lower():
            continue
        rows.append(f"{d.get('dataset_id','')}\t{d.get('study_label','')}\t{d.get('tissue_label','')}\t"
                    f"{d.get('quant_method','')}\t{d.get('condition_label','')}")
        if len(rows) > limit:
            break
    return _cap(rows, "datasets") if len(rows) > 1 else "No matching eQTL datasets."


@mcp.tool()
def eqtl_associations(dataset_id: str, gene: str = "", region: str = "", limit: int = 25) -> str:
    """eQTL associations in a dataset for a gene or genomic region (top by p-value).

    Args:
        dataset_id: eQTL Catalogue dataset id (e.g. "QTD000001", see eqtl_list_datasets).
        gene: gene symbol — resolved to a region via Ensembl (optional).
        region: "chrom:start-end" (e.g. "17:7668402-7687550"); overrides gene.
        limit: max associations (default 25).
    """
    pos = region.strip()
    if not pos:
        if not gene.strip():
            return "Provide `region` (chr:start-end) or `gene`."
        g = _get(f"{ENSEMBL}/lookup/symbol/homo_sapiens/{gene}")
        pos = f"{g.get('seq_region_name')}:{g.get('start')}-{g.get('end')}"
    data = _get(f"{EQTL}/datasets/{dataset_id}/associations", pos=pos, size=1000)
    if not isinstance(data, list) or not data:
        return f"No eQTL associations in {dataset_id} for {region or gene}."
    data.sort(key=lambda a: a.get("pvalue", 1))
    rows = [f"# {dataset_id} eQTL associations ({pos})", "variant\tgene_id\tmolecular_trait\tpvalue\tnlog10p"]
    for a in data[:max(1, limit)]:
        rows.append(f"{a.get('variant','')}\t{a.get('gene_id','')}\t{a.get('molecular_trait_id','')}\t"
                    f"{a.get('pvalue','')}\t{a.get('nlog10p','')}")
    return _cap(rows, "associations")


# ==================================================================== PheWAS
@mcp.tool()
def phewas_instances() -> str:
    """List the PheWAS portals this connector can query (FinnGen, BioBank Japan)."""
    rows = ["id\tname\trelease\tstatus"]
    for i in _PHEWAS_INSTANCES:
        rows.append(f"{i['id']}\t{i['name']}\t{i['release']}\t{i['status']}")
    return "\n".join(rows)


@mcp.tool()
def phewas_variant(rsid: str, limit: int = 30) -> str:
    """Phenome-wide associations for a variant (all trait associations, via GWAS Catalog).

    Args:
        rsid: dbSNP rsID (e.g. "rs429358").
        limit: max associations (default 30).
    """
    return gwas_associations_for_variant(rsid, limit=limit)


@mcp.tool()
def phewas_finngen_gene(gene: str, limit: int = 30) -> str:
    """Gene-based PheWAS in FinnGen: phenotypes associated at the gene's locus.

    Args:
        gene: gene symbol (e.g. "APOE").
        limit: max phenotype associations (default 30).
    """
    data = _get(f"{FINNGEN}/api/gene_phenos/{gene}")
    phenos = data.get("phenotypes", []) if isinstance(data, dict) else []
    if not phenos:
        return f"No FinnGen gene-PheWAS results for {gene}."
    def pval(p):
        return (p.get("assoc") or {}).get("pval", 1)
    phenos.sort(key=pval)
    def _varid(v):
        if isinstance(v, dict):
            return v.get("varid") or v.get("rsids") or f"{v.get('chr','')}:{v.get('pos','')}:{v.get('ref','')}:{v.get('alt','')}"
        return v or ""
    rows = [f"# FinnGen gene-PheWAS for {gene} ({len(phenos)} phenotypes)", "phenotype\tpval\tbeta\tvariant"]
    for p in phenos[:max(1, limit)]:
        ph = p.get("pheno") or {}
        a = p.get("assoc") or {}
        name = ph.get("phenostring") or ph.get("phenocode") or ""
        rows.append(f"{name}\t{a.get('pval','')}\t{a.get('beta','')}\t{_varid(p.get('variant'))}")
    return _cap(rows, "phenotypes")


@mcp.tool()
def phewas_list_phenotypes(instance: str = "finngen", limit: int = 40) -> str:
    """List phenotypes available in a PheWAS instance (FinnGen).

    Args:
        instance: PheWAS instance id (default "finngen"; see phewas_instances).
        limit: max phenotypes (default 40).
    """
    if instance != "finngen":
        return f"Phenotype listing is available for 'finngen'. '{instance}' has no public phenotype API."
    data = _get(f"{FINNGEN}/api/phenos")
    if not isinstance(data, list):
        return "No FinnGen phenotypes."
    rows = ["phenocode\tphenotype\tcategory\tcases\tcontrols"]
    for p in data[:max(1, min(limit, MAX_ROWS))]:
        rows.append(f"{p.get('phenocode','')}\t{(p.get('phenostring') or '')[:50]}\t{p.get('category','')}\t"
                    f"{p.get('num_cases','')}\t{p.get('num_controls','')}")
    return _cap(rows, "phenotypes")


@mcp.tool()
def phewas_search_phenotypes(query: str, instance: str = "finngen", limit: int = 25) -> str:
    """Search phenotypes in a PheWAS instance by name/code/category (FinnGen).

    Args:
        query: search text (e.g. "diabetes", "Alzheimer").
        instance: PheWAS instance id (default "finngen").
        limit: max results (default 25).
    """
    if instance != "finngen":
        return f"Phenotype search is available for 'finngen'. '{instance}' has no public phenotype API."
    data = _get(f"{FINNGEN}/api/phenos")
    q = query.lower().strip()
    rows = ["phenocode\tphenotype\tcategory\tcases"]
    for p in data if isinstance(data, list) else []:
        hay = f"{p.get('phenocode','')} {p.get('phenostring','')} {p.get('category','')}".lower()
        if q in hay:
            rows.append(f"{p.get('phenocode','')}\t{(p.get('phenostring') or '')[:50]}\t{p.get('category','')}\t{p.get('num_cases','')}")
        if len(rows) > limit:
            break
    return _cap(rows, "phenotypes") if len(rows) > 1 else f"No FinnGen phenotypes matching '{query}'."


if __name__ == "__main__":
    mcp.run()
