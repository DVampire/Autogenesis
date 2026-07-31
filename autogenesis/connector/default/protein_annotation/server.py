#!/usr/bin/env python3
"""Protein Annotation MCP server — protein domains, families, tissue expression and
interaction networks over three PUBLIC APIs (no auth): the EBI InterPro API
(https://www.ebi.ac.uk/interpro/api) for InterPro entries and Pfam clans/families,
the Human Protein Atlas (https://www.proteinatlas.org) for per-gene records and
search, and STRING (https://string-db.org) for protein-protein interaction networks
and cross-species homology.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import requests
from mcp.server.fastmcp import FastMCP

INTERPRO = "https://www.ebi.ac.uk/interpro/api"
HPA = "https://www.proteinatlas.org"
STRING = "https://string-db.org/api"
HDRS = {"User-Agent": "Autogenesis-protein/1.0", "Accept": "application/json"}
TIMEOUT = 30
MAX_ROWS = 40
HUMAN_TAXON = 9606

mcp = FastMCP("protein_annotation")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"InterPro {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _get_json(url, **params):
    """Generic JSON GET (used for the Human Protein Atlas)."""
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"HPA {url} -> {r.status_code}: {r.text[:120]}")
    return r.json()


def _string_tsv(method: str, identifiers, species: int = HUMAN_TAXON, **extra) -> list[dict]:
    """POST to the STRING API and parse the tab-separated response into dict rows.

    Identifiers may be a list or a pre-joined string; STRING separates them with a
    carriage return. `caller_identity` is sent as STRING requests.
    """
    ids = identifiers if isinstance(identifiers, str) else "\r".join(identifiers)
    data = {"identifiers": ids, "species": species, "caller_identity": "Autogenesis"}
    data.update(extra)
    r = requests.post(f"{STRING}/tsv/{method}", data=data,
                      headers={"User-Agent": HDRS["User-Agent"]}, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"STRING {method} -> {r.status_code}: {r.text[:150]}")
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, ln.split("\t"))) for ln in lines[1:]]


def _name(md: dict) -> str:
    n = md.get("name")
    if isinstance(n, dict):
        return n.get("name") or n.get("short") or ""
    return n or ""


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


@mcp.tool()
def search_interpro_entries(query: str, limit: int = 15) -> str:
    """Search InterPro entries (domains/families/sites) by keyword.

    Args:
        query: search text (e.g. "kinase", "zinc finger").
        limit: max entries (default 15).
    Returns 'accession<TAB>name<TAB>type' rows.
    """
    j = _get(f"{INTERPRO}/entry/interpro", search=query, page_size=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", [])
    if not res:
        return f"No InterPro entries for '{query}'."
    rows = [f"# {j.get('count','?')} entries match; showing {len(res)}", "accession\tname\ttype"]
    for x in res:
        m = x.get("metadata", {})
        rows.append(f"{m.get('accession','')}\t{_name(m)}\t{m.get('type','')}")
    return _cap(rows, "entries")


@mcp.tool()
def get_interpro_entry(interpro_id: str) -> str:
    """Get an InterPro entry's details (type, GO terms, member DBs, description).

    Args:
        interpro_id: InterPro accession (e.g. "IPR000719").
    """
    m = _get(f"{INTERPRO}/entry/interpro/{interpro_id}").get("metadata", {})
    if not m:
        return f"No InterPro entry {interpro_id}."
    go = ", ".join(g.get("identifier", "") for g in (m.get("go_terms") or [])[:8])
    members = ", ".join(f"{db}({len(ids)})" for db, ids in (m.get("member_databases") or {}).items())
    desc = ""
    d = m.get("description")
    if isinstance(d, list) and d:
        desc = (d[0].get("text", "") if isinstance(d[0], dict) else str(d[0]))
    return (f"accession: {m.get('accession','')}\nname: {_name(m)}\ntype: {m.get('type','')}\n"
            f"member_databases: {members}\ngo_terms: {go}\n"
            f"description: {' '.join(desc.replace(chr(10),' ').split())[:500]}")


@mcp.tool()
def get_domain_architecture(uniprot: str, limit: int = 30) -> str:
    """Get the domain architecture of a protein — all InterPro/member entries on it.

    Args:
        uniprot: UniProt accession (e.g. "P04637").
        limit: max entries (default 30).
    """
    j = _get(f"{INTERPRO}/entry/all/protein/uniprot/{uniprot}", page_size=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", [])
    if not res:
        return f"No domain entries for {uniprot}."
    rows = [f"# {j.get('count','?')} entries on {uniprot}", "accession\tsource_db\tname\ttype"]
    for x in res:
        m = x.get("metadata", {})
        rows.append(f"{m.get('accession','')}\t{m.get('source_database','')}\t{_name(m)}\t{m.get('type','')}")
    return _cap(rows, "entries")


@mcp.tool()
def search_pfam_clans(query: str = "", limit: int = 20) -> str:
    """Search/list Pfam clans (superfamilies grouping related families).

    Args:
        query: substring to match against clan accession/name (optional).
        limit: max clans (default 20).
    """
    q = query.lower().strip()
    rows = ["accession\tname"]
    url = f"{INTERPRO}/set/pfam"
    fetched = 0
    while url and len(rows) <= limit:
        j = _get(url, page_size=100) if "?" not in url else _get(url)
        for x in j.get("results", []):
            m = x.get("metadata", {})
            acc, name = m.get("accession", ""), _name(m)
            if q and q not in acc.lower() and q not in name.lower():
                continue
            rows.append(f"{acc}\t{name}")
            if len(rows) > limit:
                break
        url = j.get("next")
        fetched += 1
        if fetched > 5:
            break
    return _cap(rows, "clans") if len(rows) > 1 else f"No Pfam clans matching '{query}'."


@mcp.tool()
def get_pfam_clan(clan_id: str) -> str:
    """Get a Pfam clan's details (name, description).

    Args:
        clan_id: Pfam clan accession (e.g. "CL0001").
    """
    m = _get(f"{INTERPRO}/set/pfam/{clan_id}").get("metadata", {})
    if not m:
        return f"No Pfam clan {clan_id}."
    d = m.get("description")
    desc = d.get("name") if isinstance(d, dict) else (d or "")
    return f"accession: {m.get('accession','')}\nname: {_name(m)}\ndescription: {' '.join(str(desc).split())[:600]}"


@mcp.tool()
def get_pfam_family_proteins(pfam_id: str, limit: int = 20) -> str:
    """List UniProt proteins that contain a given Pfam family.

    Args:
        pfam_id: Pfam family accession (e.g. "PF00069").
        limit: max proteins (default 20).
    """
    j = _get(f"{INTERPRO}/protein/UniProt/entry/pfam/{pfam_id}", page_size=max(1, min(limit, MAX_ROWS)))
    res = j.get("results", [])
    if not res:
        return f"No proteins for Pfam {pfam_id}."
    rows = [f"# {j.get('count','?')} proteins contain {pfam_id}; showing {len(res)}", "accession\tname\tsource"]
    for x in res:
        m = x.get("metadata", {})
        rows.append(f"{m.get('accession','')}\t{_name(m)}\t{m.get('source_database','')}")
    return _cap(rows, "proteins")


@mcp.tool()
def get_pfam_family_proteomes(pfam_id: str, limit: int = 20) -> str:
    """List proteomes (organisms) in which a Pfam family is found.

    Args:
        pfam_id: Pfam family accession (e.g. "PF00069").
        limit: max proteomes (default 20).
    """
    try:
        j = _get(f"{INTERPRO}/proteome/uniprot/entry/pfam/{pfam_id}", page_size=max(1, min(limit, MAX_ROWS)))
    except (RuntimeError, requests.RequestException):
        return (f"The InterPro proteome aggregation for {pfam_id} did not respond in time "
                f"(it can be slow for large families). Try again or reduce limit.")
    res = j.get("results", [])
    if not res:
        return f"No proteomes for Pfam {pfam_id}."
    rows = [f"# {j.get('count','?')} proteomes contain {pfam_id}; showing {len(res)}", "accession\tname"]
    for x in res:
        m = x.get("metadata", {})
        rows.append(f"{m.get('accession','')}\t{_name(m)}")
    return _cap(rows, "proteomes")


# ========================================================= Human Protein Atlas
# Default columns for search_protein_atlas: gene, synonyms, Ensembl id, description,
# UniProt, chromosome, protein class, RNA tissue specificity, subcellular location.
_HPA_DEFAULT_COLS = "g,gs,eg,gd,up,chr,pc,rnats,scl"


def _hpa_search(query: str, columns: str, limit: int) -> list[dict]:
    return _get_json(f"{HPA}/api/search_download.php", search=query, format="json",
                     columns=columns, compress="no")[: max(1, limit)]


@mcp.tool()
def get_protein_atlas_gene(gene: str) -> str:
    """Get the Human Protein Atlas record for a single gene.

    Args:
        gene: Ensembl gene id (e.g. "ENSG00000141510") or gene symbol (e.g. "TP53").
            A symbol is resolved to its Ensembl id via the HPA search API first.
    Returns key HPA fields: identity, protein class, RNA/protein tissue specificity,
    subcellular location, and pathology/prognostic summaries when present.
    """
    ensg = gene
    if not gene.upper().startswith("ENSG"):
        hits = _hpa_search(gene, "g,eg", 5)
        match = next((h for h in hits if str(h.get("Gene", "")).upper() == gene.upper()), None) \
            or (hits[0] if hits else None)
        if not match:
            return f"No Human Protein Atlas gene for '{gene}'."
        ensg = match.get("Ensembl") or match.get("eg") or ""
        if not ensg:
            return f"Could not resolve '{gene}' to an Ensembl id in HPA."
    rec = _get_json(f"{HPA}/{ensg}.json")
    if not rec:
        return f"No Human Protein Atlas record for {ensg}."
    fields = ["Gene", "Ensembl", "Gene description", "Uniprot", "Chromosome",
              "Protein class", "Biological process", "Molecular function",
              "RNA tissue specificity", "RNA tissue distribution",
              "Subcellular location", "Subcellular main location",
              "Tissue expression cluster", "Antibody"]
    out = [f"# Human Protein Atlas — {rec.get('Gene', ensg)} ({ensg})"]
    for f in fields:
        v = rec.get(f)
        if v:
            if isinstance(v, (list, dict)):
                v = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            out.append(f"{f}: {str(v)[:400]}")
    return "\n".join(out) if len(out) > 1 else f"HPA record {ensg} has no populated summary fields."


@mcp.tool()
def search_protein_atlas(query: str, columns: str = "", limit: int = 15) -> str:
    """Search the Human Protein Atlas and download selected columns as rows.

    Args:
        query: HPA search query — a gene symbol/name, or a field query such as
            "protein_class:Transcription factors" or "tissue_category_rna:liver;Tissue enriched".
        columns: comma-separated HPA column codes (default gene identity + specificity/location:
            "g,gs,eg,gd,up,chr,pc,rnats,scl"). See proteinatlas.org for the full code list.
        limit: max rows (default 15).
    """
    cols = columns.strip() or _HPA_DEFAULT_COLS
    res = _hpa_search(query, cols, min(limit, MAX_ROWS))
    if not res:
        return f"No Human Protein Atlas hits for '{query}'."
    headers = list(res[0].keys())
    rows = [f"# {len(res)} HPA hits for '{query}' (columns: {cols})", "\t".join(headers)]
    for r in res:
        rows.append("\t".join(str(r.get(h, "")).replace("\t", " ").replace("\n", " ")[:120]
                              for h in headers))
    return _cap(rows, "hits")


# ================================================================= STRING
@mcp.tool()
def map_string_ids(genes: list[str], species: int = HUMAN_TAXON) -> str:
    """Map gene symbols/identifiers to STRING protein identifiers.

    Args:
        genes: list of gene symbols or identifiers (e.g. ["TP53", "EGFR", "MDM2"]).
        species: NCBI taxon id (default 9606 = human).
    Returns 'input<TAB>stringId<TAB>preferredName<TAB>annotation' rows.
    """
    rows_in = _string_tsv("get_string_ids", genes, species=species, echo_query=1)
    if not rows_in:
        return f"No STRING mapping for {genes} (species {species})."
    out = [f"# STRING id mapping (species {species})", "input\tstringId\tpreferredName\tannotation"]
    for r in rows_in:
        out.append(f"{r.get('queryItem', r.get('queryIndex',''))}\t{r.get('stringId','')}\t"
                   f"{r.get('preferredName','')}\t{r.get('annotation','')[:100]}")
    return _cap(out, "mappings")


@mcp.tool()
def get_string_network(genes: list[str], species: int = HUMAN_TAXON,
                       required_score: int = 400) -> str:
    """Get the STRING protein-protein interaction network for a set of genes.

    Args:
        genes: list of gene symbols/identifiers (e.g. ["TP53", "MDM2", "CDKN1A"]).
        species: NCBI taxon id (default 9606 = human).
        required_score: minimum combined STRING score, 0-1000 (default 400 = medium confidence).
    Returns interacting pairs with their combined and channel-specific scores.
    """
    edges = _string_tsv("network", genes, species=species, required_score=required_score)
    if not edges:
        return f"No STRING interactions among {genes} at score >= {required_score}."
    out = [f"# STRING network (species {species}, score >= {required_score}) — {len(edges)} edges",
           "proteinA\tproteinB\tcombined\texperimental\tdatabase\ttextmining"]
    for e in edges:
        out.append(f"{e.get('preferredName_A','')}\t{e.get('preferredName_B','')}\t"
                   f"{e.get('score','')}\t{e.get('escore','')}\t{e.get('dscore','')}\t{e.get('tscore','')}")
    return _cap(out, "edges")


@mcp.tool()
def get_string_similarity_scores(genes: list[str], species: int = HUMAN_TAXON) -> str:
    """Get STRING homology (Smith-Waterman bit-score) similarities among a set of proteins.

    Args:
        genes: list of gene symbols/identifiers (e.g. ["TP53", "TP63", "TP73"]).
        species: NCBI taxon id (default 9606 = human).
    Returns all-vs-all bit scores between the input proteins.
    """
    rows_h = _string_tsv("homology", genes, species=species)
    if not rows_h:
        return f"No STRING similarity scores among {genes} (species {species})."
    out = [f"# STRING homology bit-scores (species {species})", "proteinA\tproteinB\tbitscore"]
    for r in rows_h:
        out.append(f"{r.get('stringId_A','')}\t{r.get('stringId_B','')}\t{r.get('bitscore','')}")
    return _cap(out, "pairs")


@mcp.tool()
def get_string_best_similarity_hits(genes: list[str], species: int = HUMAN_TAXON,
                                    species_b: str = "") -> str:
    """Get each protein's best homolog (highest bit-score) in target species via STRING.

    Args:
        genes: list of gene symbols/identifiers in the source species.
        species: source NCBI taxon id (default 9606 = human).
        species_b: optional comma-separated target taxon id(s) to restrict hits to
            (e.g. "10090" for mouse); empty = best hit across all STRING species.
    Returns 'sourceProtein<TAB>targetTaxon<TAB>targetProtein<TAB>bitscore' rows.
    """
    extra = {}
    if species_b.strip():
        extra["species_b"] = species_b.strip()
    rows_h = _string_tsv("homology_best", genes, species=species, **extra)
    if not rows_h:
        return f"No best-homology hits for {genes} (species {species})."
    out = [f"# STRING best homology hits (source species {species})",
           "sourceProtein\ttargetTaxon\ttargetProtein\tbitscore"]
    for r in rows_h:
        out.append(f"{r.get('stringId_A','')}\t{r.get('ncbiTaxonId_B','')}\t"
                   f"{r.get('stringId_B','')}\t{r.get('bitscore','')}")
    return _cap(out, "hits")


if __name__ == "__main__":
    mcp.run()
