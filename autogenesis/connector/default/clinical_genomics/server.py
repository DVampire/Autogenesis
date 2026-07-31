#!/usr/bin/env python3
"""Clinical Genomics MCP server — clinical genomics knowledge over PUBLIC sources, no auth:

  * ClinGen      — gene-disease validity, dosage sensitivity, variant classifications (ERepo)
  * CIViC        — clinical interpretations: genes, variants, molecular profiles, evidence,
                   assertions, diseases, therapies (GraphQL)
  * Open Targets — target/disease associations, drugs (GraphQL, incl. a raw passthrough)

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import csv
import io
import json as _json
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

CLINGEN_DOSAGE = "https://ftp.clinicalgenome.org/ClinGen_gene_curation_list_GRCh38.tsv"
CLINGEN_VALIDITY = "https://search.clinicalgenome.org/kb/gene-validity/download"
EREPO = "https://erepo.clinicalgenome.org/evrepo/api/classifications"
CIVIC = "https://civicdb.org/api/graphql"
OPENTARGETS = "https://api.platform.opentargets.org/api/v4/graphql"
HDRS = {"User-Agent": "Autogenesis-clingenomics/1.0"}
TIMEOUT = 60
MAX_ROWS = 60

mcp = FastMCP("clinical_genomics")
_cache: dict = {}


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _gql(url, query, variables=None):
    r = requests.post(url, json={"query": query, "variables": variables or {}}, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GraphQL {url} -> {r.status_code}: {r.text[:200]}")
    j = r.json()
    if j.get("errors"):
        raise RuntimeError(f"GraphQL errors: {j['errors'][0].get('message')}")
    return j["data"]


# =================================================================== ClinGen
def _dosage():
    if "dosage" not in _cache:
        lines = requests.get(CLINGEN_DOSAGE, headers=HDRS, timeout=TIMEOUT).text.splitlines()
        header = next((l[1:] for l in lines if l.startswith("#") and "Haploinsufficiency Score" in l), "")
        idx = {c.strip(): i for i, c in enumerate(header.split("\t"))}
        rows = {}
        for l in lines:
            if l and not l.startswith("#"):
                cells = l.split("\t")
                rows[cells[0].upper()] = (cells, idx)
        _cache["dosage"] = rows
    return _cache["dosage"]


@mcp.tool()
def clingen_dosage_sensitivity(gene: str) -> str:
    """ClinGen dosage sensitivity (haploinsufficiency / triplosensitivity) for a gene.

    Args:
        gene: HGNC gene symbol (e.g. "BRCA1").
    """
    entry = _dosage().get(gene.upper())
    if not entry:
        return f"No ClinGen dosage curation for {gene}."
    cells, idx = entry
    def v(name):
        i = idx.get(name)
        return cells[i] if i is not None and i < len(cells) else ""
    return (f"gene: {gene}\ncytoBand: {v('cytoBand')}\n"
            f"haploinsufficiency_score: {v('Haploinsufficiency Score')}\n"
            f"haploinsufficiency: {v('Haploinsufficiency Description')}\n"
            f"triplosensitivity_score: {v('Triplosensitivity Score')}\n"
            f"triplosensitivity: {v('Triplosensitivity Description')}")


def _validity():
    if "validity" not in _cache:
        reader = list(csv.reader(io.StringIO(requests.get(CLINGEN_VALIDITY, headers=HDRS, timeout=TIMEOUT).text)))
        hi = next((i for i, r in enumerate(reader) if r and r[0].strip() == "GENE SYMBOL"), None)
        idx = {c.strip(): i for i, c in enumerate(reader[hi])} if hi is not None else {}
        data = [r for r in reader[hi + 1:] if r and not r[0].startswith("+")] if hi is not None else []
        _cache["validity"] = (data, idx)
    return _cache["validity"]


@mcp.tool()
def clingen_gene_validity(gene: str) -> str:
    """ClinGen gene-disease validity classifications for a gene.

    Args:
        gene: HGNC gene symbol (e.g. "BRCA1").
    Returns 'disease<TAB>MOI<TAB>classification<TAB>date' rows.
    """
    data, idx = _validity()
    def col(r, name):
        i = idx.get(name)
        return r[i] if i is not None and i < len(r) else ""
    hits = [r for r in data if col(r, "GENE SYMBOL").upper() == gene.upper()]
    if not hits:
        return f"No ClinGen gene-disease validity curation for {gene}."
    rows = ["disease\tMOI\tclassification\tdate"]
    for r in hits:
        rows.append(f"{col(r,'DISEASE LABEL')}\t{col(r,'MOI')}\t{col(r,'CLASSIFICATION')}\t{col(r,'CLASSIFICATION DATE')[:10]}")
    return _cap(rows, "curations")


@mcp.tool()
def clingen_variant_classifications(gene: str, limit: int = 25) -> str:
    """ClinGen Evidence Repository (ERepo) variant interpretations for a gene.

    Args:
        gene: HGNC gene symbol (e.g. "BRCA1").
        limit: max variants (default 25).
    Returns 'variant(HGVS)<TAB>caid<TAB>condition<TAB>date' rows.
    """
    r = requests.get(EREPO, params={"gene": gene}, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        return f"ERepo request failed: {r.status_code}"
    interps = r.json().get("variantInterpretations", [])
    if not interps:
        return f"No ClinGen ERepo variant interpretations for {gene}."
    rows = ["variant\tcaid\tcondition\tdate"]
    for v in interps[:max(1, limit)]:
        hgvs = v.get("hgvs")
        variant = (hgvs[0] if isinstance(hgvs, list) and hgvs else v.get("caid", ""))
        cond = v.get("condition")
        cond = cond.get("label") if isinstance(cond, dict) else (cond or "")
        rows.append(f"{variant}\t{v.get('caid','')}\t{cond}\t{v.get('publishedDate','')}")
    return _cap(rows, "variants")


@mcp.tool()
def clingen_actionability(gene: str) -> str:
    """ClinGen clinical actionability for a gene.

    NOTE: ClinGen Actionability exposes no public JSON API (web UI only), so this returns
    the direct report-search link for the gene rather than structured data.

    Args:
        gene: HGNC gene symbol (e.g. "BRCA1").
    """
    return (f"gene: {gene}\nClinGen Actionability has no public programmatic API. View curated "
            f"adult/pediatric actionability reports here:\n"
            f"https://actionability.clinicalgenome.org/ac/Adult/ui/stg2SummaryRpt?search={gene}")


# ==================================================================== CIViC
def _civic_gene_id(symbol: str) -> Optional[int]:
    g = _gql(CIVIC, 'query($s:String!){ gene(entrezSymbol:$s){ id } }', {"s": symbol}).get("gene")
    return g["id"] if g else None


@mcp.tool()
def civic_search_genes(symbol: str) -> str:
    """Look up a gene in CIViC by symbol; returns CIViC id, name, Entrez id, description.

    Args:
        symbol: gene symbol (e.g. "BRAF").
    """
    g = _gql(CIVIC, 'query($s:String!){ gene(entrezSymbol:$s){ id name entrezId description } }',
             {"s": symbol}).get("gene")
    if not g:
        return f"No CIViC gene '{symbol}'."
    return f"civic_id: {g['id']}\nname: {g['name']}\nentrezId: {g.get('entrezId')}\ndescription: {(g.get('description') or '')[:300]}"


@mcp.tool()
def civic_gene_variants(gene: str, limit: int = 40) -> str:
    """List CIViC variants curated for a gene.

    Args:
        gene: gene symbol (e.g. "BRAF").
        limit: max variants (default 40).
    """
    gid = _civic_gene_id(gene)
    if not gid:
        return f"No CIViC gene '{gene}'."
    nodes = _gql(CIVIC, 'query($id:Int!){ variants(geneId:$id){ nodes{ id name } } }', {"id": gid})["variants"]["nodes"]
    rows = ["variant_id\tname"] + [f"{n['id']}\t{n['name']}" for n in nodes[:max(1, limit)]]
    return _cap(rows, "variants")


@mcp.tool()
def civic_get_variant(variant_id: int) -> str:
    """Get a CIViC variant's details.

    Args:
        variant_id: CIViC variant id (integer).
    """
    v = _gql(CIVIC, 'query($id:Int!){ variant(id:$id){ id name feature{ name } variantAliases } }',
             {"id": variant_id}).get("variant")
    if not v:
        return f"No CIViC variant {variant_id}."
    return (f"id: {v['id']}\nname: {v['name']}\ngene/feature: {(v.get('feature') or {}).get('name','')}\n"
            f"aliases: {', '.join(v.get('variantAliases') or [])}")


@mcp.tool()
def civic_search_variants(query: str, limit: int = 25) -> str:
    """Search CIViC variants by name (e.g. "V600E").

    Args:
        query: variant name substring.
        limit: max results (default 25).
    """
    nodes = _gql(CIVIC, 'query($n:String!,$f:Int!){ browseVariants(variantName:$n, first:$f){ nodes{ id name } } }',
                 {"n": query, "f": max(1, limit)})["browseVariants"]["nodes"]
    rows = ["variant_id\tname"] + [f"{n['id']}\t{n['name']}" for n in nodes]
    return "\n".join(rows) if len(rows) > 1 else f"No CIViC variants matching '{query}'."


@mcp.tool()
def civic_get_molecular_profile(molecular_profile_id: int) -> str:
    """Get a CIViC molecular profile (a variant or combination interpreted clinically).

    Args:
        molecular_profile_id: CIViC molecular profile id (integer).
    """
    m = _gql(CIVIC, 'query($id:Int!){ molecularProfile(id:$id){ id name description } }',
             {"id": molecular_profile_id}).get("molecularProfile")
    if not m:
        return f"No CIViC molecular profile {molecular_profile_id}."
    return f"id: {m['id']}\nname: {m['name']}\ndescription: {(m.get('description') or '')[:400]}"


@mcp.tool()
def civic_search_molecular_profiles(query: str, limit: int = 25) -> str:
    """Search CIViC molecular profiles by name (e.g. "BRAF V600E").

    Args:
        query: molecular profile name substring.
        limit: max results (default 25).
    """
    nodes = _gql(CIVIC, 'query($n:String!,$f:Int!){ browseMolecularProfiles(molecularProfileName:$n, first:$f)'
                 '{ nodes{ id name molecularProfileScore } } }', {"n": query, "f": max(1, limit)})["browseMolecularProfiles"]["nodes"]
    rows = ["mp_id\tname\tscore"] + [f"{n['id']}\t{n['name']}\t{n.get('molecularProfileScore','')}" for n in nodes]
    return "\n".join(rows) if len(rows) > 1 else f"No CIViC molecular profiles matching '{query}'."


@mcp.tool()
def civic_get_evidence_item(evidence_id: int) -> str:
    """Get a CIViC evidence item's clinical interpretation.

    Args:
        evidence_id: CIViC evidence item id (integer).
    """
    e = _gql(CIVIC, 'query($id:Int!){ evidenceItem(id:$id){ id evidenceType significance evidenceLevel '
             'disease{ name } therapies{ name } description } }', {"id": evidence_id}).get("evidenceItem")
    if not e:
        return f"No CIViC evidence item {evidence_id}."
    return (f"id: {e['id']}\ntype: {e.get('evidenceType')}\nsignificance: {e.get('significance')}\n"
            f"level: {e.get('evidenceLevel')}\ndisease: {(e.get('disease') or {}).get('name','')}\n"
            f"therapies: {', '.join(t['name'] for t in e.get('therapies') or [])}\n"
            f"description: {(e.get('description') or '')[:400]}")


@mcp.tool()
def civic_search_evidence(disease: str = "", limit: int = 20) -> str:
    """Search CIViC evidence items, optionally filtered by disease name.

    Args:
        disease: disease name filter (e.g. "Melanoma"); empty for latest evidence.
        limit: max items (default 20).
    """
    nodes = _gql(CIVIC, 'query($d:String,$f:Int!){ evidenceItems(diseaseName:$d, first:$f){ nodes{ id evidenceType '
                 'significance disease{ name } therapies{ name } } } }', {"d": disease or None, "f": max(1, limit)})["evidenceItems"]["nodes"]
    rows = ["id\ttype\tsignificance\tdisease\ttherapies"]
    for e in nodes:
        rows.append(f"{e['id']}\t{e.get('evidenceType')}\t{e.get('significance')}\t"
                    f"{(e.get('disease') or {}).get('name','')}\t{','.join(t['name'] for t in e.get('therapies') or [])}")
    return _cap(rows, "evidence") if len(rows) > 1 else "No evidence items found."


@mcp.tool()
def civic_get_assertion(assertion_id: int) -> str:
    """Get a CIViC assertion (a summarized clinical statement over evidence).

    Args:
        assertion_id: CIViC assertion id (integer).
    """
    a = _gql(CIVIC, 'query($id:Int!){ assertion(id:$id){ id assertionType assertionDirection ampLevel summary '
             'disease{ name } therapies{ name } } }', {"id": assertion_id}).get("assertion")
    if not a:
        return f"No CIViC assertion {assertion_id}."
    return (f"id: {a['id']}\ntype: {a.get('assertionType')}\ndirection: {a.get('assertionDirection')}\n"
            f"ampLevel: {a.get('ampLevel')}\ndisease: {(a.get('disease') or {}).get('name','')}\n"
            f"therapies: {', '.join(t['name'] for t in a.get('therapies') or [])}\nsummary: {(a.get('summary') or '')[:400]}")


@mcp.tool()
def civic_search_assertions(disease: str = "", limit: int = 20) -> str:
    """Search CIViC assertions, optionally filtered by disease name.

    Args:
        disease: disease name filter (e.g. "Melanoma"); empty for latest.
        limit: max assertions (default 20).
    """
    nodes = _gql(CIVIC, 'query($d:String,$f:Int!){ assertions(diseaseName:$d, first:$f){ nodes{ id assertionType '
                 'assertionDirection } } }', {"d": disease or None, "f": max(1, limit)})["assertions"]["nodes"]
    rows = ["id\ttype\tdirection"] + [f"{a['id']}\t{a.get('assertionType')}\t{a.get('assertionDirection')}" for a in nodes]
    return "\n".join(rows) if len(rows) > 1 else "No assertions found."


@mcp.tool()
def civic_search_diseases(query: str, limit: int = 25) -> str:
    """Search CIViC diseases by name.

    Args:
        query: disease name substring (e.g. "melanoma").
        limit: max results (default 25).
    """
    nodes = _gql(CIVIC, 'query($n:String!,$f:Int!){ browseDiseases(name:$n, first:$f){ nodes{ id name doid } } }',
                 {"n": query, "f": max(1, limit)})["browseDiseases"]["nodes"]
    rows = ["disease_id\tname\tDOID"] + [f"{n['id']}\t{n['name']}\t{n.get('doid','')}" for n in nodes]
    return "\n".join(rows) if len(rows) > 1 else f"No CIViC diseases matching '{query}'."


@mcp.tool()
def civic_search_therapies(query: str, limit: int = 25) -> str:
    """Search CIViC therapies (drugs) by name.

    Args:
        query: therapy name substring (e.g. "vemurafenib").
        limit: max results (default 25).
    """
    nodes = _gql(CIVIC, 'query($n:String!,$f:Int!){ browseTherapies(name:$n, first:$f){ nodes{ id name ncitId } } }',
                 {"n": query, "f": max(1, limit)})["browseTherapies"]["nodes"]
    rows = ["therapy_id\tname\tNCIt"] + [f"{n['id']}\t{n['name']}\t{n.get('ncitId','')}" for n in nodes]
    return "\n".join(rows) if len(rows) > 1 else f"No CIViC therapies matching '{query}'."


# ============================================================== Open Targets
def _ot_resolve(name: str, entity: str) -> str:
    """Resolve a symbol/name to an Open Targets id (pass ENSG/EFO/MONDO/CHEMBL ids through)."""
    up = name.upper()
    if up.startswith(("ENSG", "EFO_", "MONDO_", "CHEMBL", "HP_", "ORPHANET")):
        return name
    hits = _gql(OPENTARGETS, 'query($q:String!,$e:[String!]){ search(queryString:$q, entityNames:$e){ hits{ id } } }',
                {"q": name, "e": [entity]})["search"]["hits"]
    if not hits:
        raise RuntimeError(f"No Open Targets {entity} for '{name}'.")
    return hits[0]["id"]


@mcp.tool()
def open_targets_graphql(query: str, variables: str = "") -> str:
    """Run an arbitrary Open Targets Platform GraphQL query (escape hatch for any query).

    Args:
        query: a GraphQL query string against https://api.platform.opentargets.org/api/v4/graphql.
        variables: optional JSON string of query variables.
    Returns the JSON `data` payload.
    """
    vars_obj = {}
    if variables.strip():
        try:
            vars_obj = _json.loads(variables)
        except Exception as e:
            return f"Invalid `variables` JSON: {e}"
    data = _gql(OPENTARGETS, query, vars_obj)
    return _json.dumps(data, ensure_ascii=False, indent=2)[:6000]


@mcp.tool()
def open_targets_disease_targets(disease: str, limit: int = 25) -> str:
    """List targets associated with a disease, ranked by Open Targets association score.

    Args:
        disease: disease name or EFO/MONDO id (e.g. "melanoma" or "MONDO_0005105").
        limit: max targets (default 25).
    """
    eid = _ot_resolve(disease, "disease")
    d = _gql(OPENTARGETS, 'query($id:String!,$n:Int!){ disease(efoId:$id){ name associatedTargets(page:{index:0,size:$n})'
             '{ rows{ target{ approvedSymbol id } score } } } }', {"id": eid, "n": max(1, limit)})["disease"]
    if not d:
        return f"No Open Targets disease for '{disease}'."
    rows = [f"# {d['name']} ({eid}) — associated targets", "symbol\tscore\tensemblId"]
    for r in d["associatedTargets"]["rows"]:
        rows.append(f"{r['target']['approvedSymbol']}\t{r['score']:.3f}\t{r['target']['id']}")
    return _cap(rows, "targets")


@mcp.tool()
def open_targets_disease_drugs(disease: str, limit: int = 25) -> str:
    """List drugs and clinical candidates for a disease from Open Targets.

    Args:
        disease: disease name or EFO/MONDO id (e.g. "melanoma").
        limit: max drugs (default 25).
    """
    eid = _ot_resolve(disease, "disease")
    d = _gql(OPENTARGETS, 'query($id:String!){ disease(efoId:$id){ name drugAndClinicalCandidates{ count '
             'rows{ drug{ id name drugType } maxClinicalStage } } } }', {"id": eid})["disease"]
    if not d:
        return f"No Open Targets disease for '{disease}'."
    kd = d.get("drugAndClinicalCandidates") or {}
    rows = [f"# {d['name']} ({eid}) — {kd.get('count',0)} drugs/candidates", "drug\ttype\tmaxStage\tchemblId"]
    for r in (kd.get("rows") or [])[:max(1, limit)]:
        dr = r.get("drug") or {}
        rows.append(f"{dr.get('name','')}\t{dr.get('drugType','')}\t{r.get('maxClinicalStage','')}\t{dr.get('id','')}")
    return _cap(rows, "drugs") if len(rows) > 2 else f"No drugs listed for '{disease}'."


@mcp.tool()
def open_targets_drug(drug: str) -> str:
    """Get an Open Targets drug's type, phase, mechanism(s), and indications.

    Args:
        drug: drug name or ChEMBL id (e.g. "vemurafenib" or "CHEMBL1229517").
    """
    cid = _ot_resolve(drug, "drug")
    d = _gql(OPENTARGETS, 'query($id:String!){ drug(chemblId:$id){ id name drugType maximumClinicalStage '
             'mechanismsOfAction{ rows{ mechanismOfAction } } indications{ rows{ disease{ name } } } } }', {"id": cid})["drug"]
    if not d:
        return f"No Open Targets drug for '{drug}'."
    moa = "; ".join(m["mechanismOfAction"] for m in (d.get("mechanismsOfAction") or {}).get("rows", []))
    inds = ", ".join((i.get("disease") or {}).get("name", "") for i in (d.get("indications") or {}).get("rows", [])[:10])
    return (f"id: {d['id']}\nname: {d['name']}\ntype: {d.get('drugType')}\n"
            f"maxClinicalStage: {d.get('maximumClinicalStage')}\nmechanisms: {moa}\nindications: {inds}")


if __name__ == "__main__":
    mcp.run()
