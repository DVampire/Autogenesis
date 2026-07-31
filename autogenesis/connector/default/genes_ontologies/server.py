#!/usr/bin/env python3
"""Genes & Ontologies MCP server — gene identity and ontologies over PUBLIC APIs, no auth:

  * MyGene.info  — gene identity/annotation queries
  * EBI OLS4     — ontology listing, term search, term lookup
  * QuickGO      — Gene Ontology annotations
  * UniProt      — protein entries
  * Reactome     — pathway mapping

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

# Official UniProt accession pattern (so gene symbols like "TP53" are NOT mistaken for one).
_UNIPROT_ACC = re.compile(r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$")

MYGENE = "https://mygene.info/v3"
OLS = "https://www.ebi.ac.uk/ols4/api"
QUICKGO = "https://www.ebi.ac.uk/QuickGO/services"
UNIPROT = "https://rest.uniprot.org/uniprotkb"
REACTOME = "https://reactome.org/ContentService"
HDRS = {"User-Agent": "Autogenesis-genes/1.0", "Accept": "application/json"}
TIMEOUT = 45
MAX_ROWS = 50

# obo_id prefix -> OLS ontology id
_ONTO = {"GO": "go", "CL": "cl", "CHEBI": "chebi", "HP": "hp", "MONDO": "mondo",
         "UBERON": "uberon", "EFO": "efo", "DOID": "doid", "PR": "pr", "SO": "so",
         "MP": "mp", "NCBITAXON": "ncbitaxon"}

mcp = FastMCP("genes_ontologies")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:200]}")
    return r.json()


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _gene_to_uniprot(gene: str) -> Optional[str]:
    """Resolve a gene symbol (or pass-through UniProt accession) to a UniProt accession."""
    if _UNIPROT_ACC.match(gene):
        return gene  # already a UniProt accession (e.g. P04637)
    j = _get(f"{MYGENE}/query", q=gene, species="human", size=1, fields="uniprot")
    hits = j.get("hits", [])
    if not hits:
        return None
    up = (hits[0].get("uniprot") or {}).get("Swiss-Prot")
    return up[0] if isinstance(up, list) else up


# --------------------------------------------------------------------------- #
@mcp.tool()
def query_genes(query: str, species: str = "human", limit: int = 10) -> str:
    """Query genes by symbol/name/id via MyGene.info; returns cross-reference identifiers.

    Args:
        query: gene symbol, name, or id (e.g. "TP53", "CDK2").
        species: species (default "human").
        limit: max hits (default 10).
    Returns 'symbol<TAB>name<TAB>entrez<TAB>ensembl<TAB>uniprot' rows.
    """
    j = _get(f"{MYGENE}/query", q=query, species=species, size=max(1, limit),
             fields="symbol,name,entrezgene,ensembl.gene,uniprot.Swiss-Prot")
    hits = j.get("hits", [])
    if not hits:
        return f"No genes for '{query}'."
    rows = ["symbol\tname\tentrez\tensembl\tuniprot"]
    for h in hits:
        ens = h.get("ensembl", {})
        ens = ens.get("gene") if isinstance(ens, dict) else (ens[0].get("gene") if isinstance(ens, list) and ens else "")
        up = (h.get("uniprot") or {}).get("Swiss-Prot")
        up = up[0] if isinstance(up, list) else (up or "")
        rows.append(f"{h.get('symbol','')}\t{h.get('name','')}\t{h.get('entrezgene','')}\t{ens or ''}\t{up}")
    return _cap(rows, "genes")


@mcp.tool()
def list_ontologies(limit: int = 30) -> str:
    """List ontologies available in EBI OLS (id + title).

    Args:
        limit: max ontologies (default 30).
    """
    j = _get(f"{OLS}/ontologies", size=max(1, min(limit, MAX_ROWS)))
    onts = j.get("_embedded", {}).get("ontologies", [])
    rows = ["ontologyId\ttitle"]
    for o in onts:
        rows.append(f"{o.get('ontologyId','')}\t{(o.get('config') or {}).get('title','')}")
    return _cap(rows, "ontologies")


@mcp.tool()
def search_ontology_terms(query: str, ontology: str = "", limit: int = 15) -> str:
    """Search ontology terms across EBI OLS, optionally restricted to one ontology.

    Args:
        query: search text (e.g. "apoptosis").
        ontology: OLS ontology id to restrict to (e.g. "go", "hp"); empty for all.
        limit: max results (default 15).
    Returns 'term_id<TAB>label<TAB>ontology' rows.
    """
    params = {"q": query, "rows": max(1, min(limit, MAX_ROWS))}
    if ontology.strip():
        params["ontology"] = ontology.strip().lower()
    docs = _get(f"{OLS}/search", **params).get("response", {}).get("docs", [])
    rows = ["term_id\tlabel\tontology"] + [f"{d.get('obo_id','')}\t{d.get('label','')}\t{d.get('ontology_name','')}" for d in docs]
    return "\n".join(rows) if len(rows) > 1 else f"No ontology terms for '{query}'."


@mcp.tool()
def get_ontology_term(term_id: str, ontology: str = "") -> str:
    """Get an ontology term's label, definition, and synonyms from EBI OLS.

    Args:
        term_id: an OBO id (e.g. "GO:0006915", "HP:0001250"). Ontology is inferred
            from the prefix if not given.
        ontology: OLS ontology id (optional; inferred from term_id prefix otherwise).
    """
    onto = ontology.strip().lower() or _ONTO.get(term_id.split(":")[0].upper(), term_id.split(":")[0].lower())
    terms = _get(f"{OLS}/ontologies/{onto}/terms", obo_id=term_id).get("_embedded", {}).get("terms", [])
    if not terms:
        return f"No term {term_id} in ontology '{onto}'."
    t = terms[0]
    desc = t.get("description") or []
    syn = t.get("synonyms") or []
    return (f"id: {t.get('obo_id','')}\nlabel: {t.get('label','')}\nontology: {onto}\n"
            f"definition: {(desc[0] if isinstance(desc, list) and desc else '')}\n"
            f"synonyms: {', '.join(syn[:10])}")


@mcp.tool()
def get_go_annotations(gene: str, limit: int = 25) -> str:
    """Get Gene Ontology annotations for a gene/protein via QuickGO.

    Args:
        gene: gene symbol or UniProt accession (e.g. "TP53" or "P04637").
        limit: max annotations (default 25).
    Returns 'GO_id<TAB>aspect<TAB>qualifier<TAB>evidence' rows (deduplicated).
    """
    acc = _gene_to_uniprot(gene)
    if not acc:
        return f"Could not resolve '{gene}' to a UniProt accession."
    res = _get(f"{QUICKGO}/annotation/search", geneProductId=acc, limit=min(100, MAX_ROWS)).get("results", [])
    if not res:
        return f"No GO annotations for {gene} ({acc})."
    seen, rows = set(), [f"# GO annotations for {gene} ({acc})", "GO_id\taspect\tqualifier\tevidence"]
    for r in res:
        key = (r.get("goId"), r.get("qualifier"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(f"{r.get('goId','')}\t{r.get('goAspect','')}\t{r.get('qualifier','')}\t{r.get('goEvidence','')}")
        if len(rows) > limit + 2:
            break
    return _cap(rows, "annotations")


@mcp.tool()
def get_uniprot_entries(query: str, limit: int = 5) -> str:
    """Get UniProt protein entries by accession or a search query (human, reviewed).

    Args:
        query: UniProt accession (e.g. "P04637") or gene/protein search text (e.g. "TP53").
        limit: max entries (default 5).
    """
    if _UNIPROT_ACC.match(query):
        q = f"accession:{query}"
    else:
        q = f"(gene:{query} OR protein_name:{query}) AND organism_id:9606 AND reviewed:true"
    j = _get(f"{UNIPROT}/search", query=q, fields="accession,id,protein_name,gene_names,organism_name,length",
             size=max(1, min(limit, 20)), format="json")
    res = j.get("results", [])
    if not res:
        return f"No UniProt entries for '{query}'."
    out = []
    for r in res:
        name = (((r.get("proteinDescription") or {}).get("recommendedName") or {}).get("fullName") or {}).get("value", "")
        genes = ", ".join(g.get("geneName", {}).get("value", "") for g in (r.get("genes") or []) if g.get("geneName"))
        out.append(f"## {r.get('primaryAccession','')} ({r.get('uniProtkbId','')})\n"
                   f"protein: {name}\ngenes: {genes}\nlength: {(r.get('sequence') or {}).get('length','')}")
    return "\n\n".join(out)


@mcp.tool()
def map_reactome_pathways(gene: str, limit: int = 25) -> str:
    """Map a gene/protein to Reactome pathways it participates in.

    Args:
        gene: gene symbol or UniProt accession (e.g. "TP53" or "P04637").
        limit: max pathways (default 25).
    Returns 'stId<TAB>pathway' rows.
    """
    acc = _gene_to_uniprot(gene)
    if not acc:
        return f"Could not resolve '{gene}' to a UniProt accession."
    try:
        data = _get(f"{REACTOME}/data/mapping/UniProt/{acc}/pathways", species="9606")
    except RuntimeError:
        return f"No Reactome pathways for {gene} ({acc})."
    if not isinstance(data, list) or not data:
        return f"No Reactome pathways for {gene} ({acc})."
    rows = [f"# Reactome pathways for {gene} ({acc})", "stId\tpathway"]
    for p in data[:max(1, limit)]:
        rows.append(f"{p.get('stId','')}\t{p.get('displayName','')}")
    return _cap(rows, "pathways")


if __name__ == "__main__":
    mcp.run()
