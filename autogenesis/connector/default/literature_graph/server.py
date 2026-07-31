#!/usr/bin/env python3
"""Literature Graph MCP server — scholarly literature over PUBLIC APIs, no auth:

  * OpenAlex (api.openalex.org)        — works, citations, references, authors, venues
  * arXiv    (export.arxiv.org/api)    — preprint search and retrieval

Endpoint mappings referenced from open-source OpenAlex/arXiv MCP servers
(e.g. benedict2310/Scientific-Papers-MCP). Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

OPENALEX = "https://api.openalex.org"
ARXIV = "http://export.arxiv.org/api/query"
# OpenAlex "polite pool": identify with a mailto.
HDRS = {"User-Agent": "Autogenesis-literature/1.0 (mailto:agent@autogenesis.local)",
        "Accept": "application/json"}
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
TIMEOUT = 40
MAX_ROWS = 40

mcp = FastMCP("literature_graph")


def _get(url, **params):
    r = requests.get(url, params=params, headers=HDRS, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:150]}")
    return r


def _oid(x: str) -> str:
    """Normalize an OpenAlex id/URL to its bare form (e.g. W2556159813)."""
    return x.rstrip("/").split("/")[-1]


def _abstract(work: dict) -> str:
    inv = work.get("abstract_inverted_index")
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def _cap(rows, scope):
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS] + [f"... ({len(rows) - MAX_ROWS} more {scope} truncated)"]
    return "\n".join(rows)


def _work_row(w: dict) -> str:
    return (f"{_oid(w.get('id',''))}\t{(w.get('title') or '')[:70]}\t{w.get('publication_year','')}\t"
            f"cited:{w.get('cited_by_count',0)}\t{(w.get('doi') or '').replace('https://doi.org/','')}")


# ================================================================= OpenAlex
@mcp.tool()
def openalex_search_works(query: str, limit: int = 15) -> str:
    """Search scholarly works (papers) in OpenAlex by keyword.

    Args:
        query: search text (e.g. "CRISPR gene editing").
        limit: max works (default 15).
    Returns 'id<TAB>title<TAB>year<TAB>citations<TAB>doi' rows.
    """
    j = _get(f"{OPENALEX}/works", search=query, **{"per-page": max(1, min(limit, MAX_ROWS))}).json()
    works = j.get("results", [])
    if not works:
        return f"No works for '{query}'."
    rows = [f"# {j.get('meta',{}).get('count','?')} works match; showing {len(works)}", "id\ttitle\tyear\tcitations\tdoi"]
    rows += [_work_row(w) for w in works]
    return _cap(rows, "works")


@mcp.tool()
def openalex_get_work(work_id: str) -> str:
    """Get a work's full metadata (authors, venue, year, citations, abstract).

    Args:
        work_id: OpenAlex id (e.g. "W2556159813") or a DOI.
    """
    wid = work_id if work_id.startswith(("http", "10.")) else _oid(work_id)
    if work_id.startswith("10."):
        wid = f"https://doi.org/{work_id}"
    w = _get(f"{OPENALEX}/works/{wid}").json()
    authors = ", ".join(a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:12])
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
    abstract_text = _abstract(w)
    return (f"id: {_oid(w.get('id',''))}\ntitle: {w.get('title','')}\nyear: {w.get('publication_year','')}\n"
            f"venue: {venue}\nauthors: {authors}\ncited_by: {w.get('cited_by_count',0)}\n"
            f"references: {len(w.get('referenced_works',[]))}\ndoi: {(w.get('doi') or '')}\n"
            f"abstract: {abstract_text[:600]}")


@mcp.tool()
def openalex_citations(work_id: str, limit: int = 20) -> str:
    """List works that CITE a given work (incoming citations).

    Args:
        work_id: OpenAlex work id (e.g. "W2556159813").
        limit: max citing works (default 20).
    """
    wid = _oid(work_id)
    j = _get(f"{OPENALEX}/works", filter=f"cites:{wid}", **{"per-page": max(1, min(limit, MAX_ROWS))}).json()
    works = j.get("results", [])
    if not works:
        return f"No citing works for {wid}."
    rows = [f"# {j.get('meta',{}).get('count',0)} works cite {wid}", "id\ttitle\tyear\tcitations\tdoi"]
    rows += [_work_row(w) for w in works]
    return _cap(rows, "citing works")


@mcp.tool()
def openalex_references(work_id: str, limit: int = 25) -> str:
    """List the works REFERENCED BY a given work (its bibliography).

    Args:
        work_id: OpenAlex work id (e.g. "W2556159813").
        limit: max references (default 25).
    """
    w = _get(f"{OPENALEX}/works/{_oid(work_id)}").json()
    refs = [_oid(r) for r in (w.get("referenced_works") or [])][:max(1, min(limit, MAX_ROWS))]
    if not refs:
        return f"No referenced works listed for {_oid(work_id)}."
    try:
        j = _get(f"{OPENALEX}/works", filter=f"openalex_id:{'|'.join(refs)}", **{"per-page": len(refs)}).json()
        rows = [f"# {len(refs)} references of {_oid(work_id)}", "id\ttitle\tyear\tcitations\tdoi"]
        rows += [_work_row(x) for x in j.get("results", [])]
        return _cap(rows, "references")
    except RuntimeError:
        return f"# references of {_oid(work_id)} (ids)\n" + "\n".join(refs)


@mcp.tool()
def openalex_search_authors(query: str, limit: int = 15) -> str:
    """Search authors in OpenAlex by name.

    Args:
        query: author name (e.g. "Jennifer Doudna").
        limit: max authors (default 15).
    Returns 'id<TAB>name<TAB>works<TAB>citations<TAB>institution' rows.
    """
    j = _get(f"{OPENALEX}/authors", search=query, **{"per-page": max(1, min(limit, MAX_ROWS))}).json()
    authors = j.get("results", [])
    if not authors:
        return f"No authors for '{query}'."
    rows = ["id\tname\tworks\tcitations\tinstitution"]
    for a in authors:
        inst = (a.get("last_known_institutions") or [{}])[0].get("display_name", "") if a.get("last_known_institutions") else (a.get("last_known_institution") or {}).get("display_name", "")
        rows.append(f"{_oid(a.get('id',''))}\t{a.get('display_name','')}\t{a.get('works_count','')}\t{a.get('cited_by_count','')}\t{inst}")
    return _cap(rows, "authors")


@mcp.tool()
def openalex_get_author(author_id: str) -> str:
    """Get an author's profile (works, citations, institution, top topics).

    Args:
        author_id: OpenAlex author id (e.g. "A5085943412").
    """
    a = _get(f"{OPENALEX}/authors/{_oid(author_id)}").json()
    inst = (a.get("last_known_institutions") or [{}])[0].get("display_name", "") if a.get("last_known_institutions") else ""
    topics = ", ".join(t.get("display_name", "") for t in (a.get("topics") or [])[:6])
    orcid = a.get("orcid") or ""
    return (f"id: {_oid(a.get('id',''))}\nname: {a.get('display_name','')}\norcid: {orcid}\n"
            f"institution: {inst}\nworks_count: {a.get('works_count','')}\ncited_by: {a.get('cited_by_count','')}\n"
            f"h_index: {(a.get('summary_stats') or {}).get('h_index','')}\ntop_topics: {topics}")


@mcp.tool()
def openalex_venue_info(query: str) -> str:
    """Get info on a publication venue/source (journal) by name or OpenAlex source id.

    Args:
        query: venue name (e.g. "Nature") or a source id (e.g. "S137773608").
    """
    if query.upper().startswith("S") and query[1:].isdigit():
        srcs = [_get(f"{OPENALEX}/sources/{_oid(query)}").json()]
    else:
        srcs = _get(f"{OPENALEX}/sources", search=query, **{"per-page": 3}).json().get("results", [])
    if not srcs:
        return f"No venue for '{query}'."
    out = []
    for s in srcs[:3]:
        out.append(f"## {s.get('display_name','')} ({_oid(s.get('id',''))})\n"
                   f"publisher: {s.get('host_organization_name','')}\ntype: {s.get('type','')}\n"
                   f"ISSN-L: {s.get('issn_l','')}\nworks: {s.get('works_count','')}\n"
                   f"cited_by: {s.get('cited_by_count','')}\nh_index: {(s.get('summary_stats') or {}).get('h_index','')}")
    return "\n\n".join(out)


# ==================================================================== arXiv
def _arxiv_entries(xml_text: str, limit: int) -> str:
    root = ET.fromstring(xml_text)
    ents = root.findall("a:entry", ATOM)
    if not ents:
        return "No arXiv papers found."
    out = []
    for e in ents[:limit]:
        aid = (e.find("a:id", ATOM).text or "").split("/abs/")[-1]
        title = " ".join((e.find("a:title", ATOM).text or "").split())
        authors = ", ".join(a.find("a:name", ATOM).text for a in e.findall("a:author", ATOM)[:8])
        pub = (e.find("a:published", ATOM).text or "")[:10]
        summ = " ".join((e.find("a:summary", ATOM).text or "").split())[:300]
        out.append(f"## {aid}  ({pub})\n{title}\nauthors: {authors}\n{summ}")
    return "\n\n".join(out)


@mcp.tool()
def arxiv_search(query: str, limit: int = 10) -> str:
    """Search arXiv preprints by query.

    Args:
        query: search text (e.g. "diffusion models"); supports arXiv field prefixes
            like "au:", "ti:", "cat:".
        limit: max papers (default 10).
    """
    sq = query if ":" in query else f"all:{query}"
    r = _get(ARXIV, search_query=sq, start=0, max_results=max(1, min(limit, MAX_ROWS)),
             sortBy="relevance", sortOrder="descending")
    return _arxiv_entries(r.text, limit)


@mcp.tool()
def arxiv_get_papers(arxiv_ids: str, limit: int = 10) -> str:
    """Fetch specific arXiv papers by their ids.

    Args:
        arxiv_ids: comma-separated arXiv ids (e.g. "2202.07171,1706.03762").
        limit: max papers (default 10).
    """
    ids = ",".join(i.strip() for i in arxiv_ids.split(",") if i.strip())
    if not ids:
        return "Provide one or more arXiv ids."
    r = _get(ARXIV, id_list=ids, max_results=max(1, min(limit, MAX_ROWS)))
    return _arxiv_entries(r.text, limit)


if __name__ == "__main__":
    mcp.run()
