"""arXiv."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class ArxivTool(PluginTool):
    """arXiv."""

    name: str = 'arxiv'
    display_name: str = 'arXiv'
    description: str = 'Search and retrieve papers from arXiv.org.'

    async def __call__(self, search_query: str = "", search_type: str = "all", max_results: int = 10, **kwargs) -> Response:
        import urllib.parse, urllib.request
        from xml.etree import ElementTree as ET
        q = str(search_query or "").strip()
        if not q:
            return self._fail("arxiv: 'search_query' is required.")
        prefix = {"title": "ti", "abstract": "abs", "author": "au", "cat": "cat"}.get(search_type, "")
        query = f"{prefix}:{q}" if prefix else q
        url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": query, "max_results": str(int(max_results))})
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname != "export.arxiv.org":
                return self._fail("arxiv: refused non-arxiv URL.")
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 — host validated above
                text = resp.read().decode("utf-8")
            root = ET.fromstring(text)  # noqa: S314 — arxiv is trusted
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"arxiv: {type(exc).__name__}: {exc}")
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        def _t(entry, tag):
            el = entry.find(tag, ns)
            return el.text.strip() if el is not None and el.text else None
        records = []
        for entry in root.findall("atom:entry", ns):
            records.append({
                "id": _t(entry, "atom:id"), "title": _t(entry, "atom:title"),
                "summary": _t(entry, "atom:summary"), "published": _t(entry, "atom:published"),
                "authors": [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)],
                "categories": [c.get("term") for c in entry.findall("atom:category", ns)],
            })
        return self._ok(f"arXiv returned {len(records)} papers for '{q}'.",
                        query=q, records=records, count=len(records))
