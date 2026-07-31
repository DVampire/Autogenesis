"""Wikipedia."""

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class WikipediaTool(PluginTool):
    """Wikipedia."""

    name: str = 'wikipedia'
    display_name: str = 'Wikipedia'
    description: str = 'Call Wikipedia API.'

    async def __call__(self, input_value: str = "", k: int = 4, lang: str = "en", load_all_available_meta: bool = False, doc_content_chars_max: int = 4000, **kwargs) -> Response:
        query = str(input_value or "").strip()
        if not query:
            return self._fail("wikipedia.wikipedia: 'input_value' is required.")
        try:
            from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
            wrapper = WikipediaAPIWrapper(top_k_results=int(k), lang=lang,
                                          load_all_available_meta=load_all_available_meta,
                                          doc_content_chars_max=int(doc_content_chars_max))
            docs = wrapper.load(query)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"wikipedia.wikipedia: {type(exc).__name__}: {exc}")
        records = [{"title": d.metadata.get("title", ""), "summary": d.metadata.get("summary", ""),
                    "source": d.metadata.get("source", ""), "content": d.page_content} for d in docs]
        return self._ok(f"Wikipedia returned {len(records)} pages for '{query}'.",
                        query=query, records=records, count=len(records))
