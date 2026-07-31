"""Tavily page extraction."""

from autogenesis.plugins.types import PluginTool
from autogenesis.response.types import Response


class TavilyExtractTool(PluginTool):
    """Pull the readable text out of web pages."""

    name: str = "tavily_extract"
    display_name: str = "Tavily Extract"
    description: str = "Fetch one or more URLs and return their readable text content."

    async def __call__(self, urls: str = "", api_key: str = "", extract_depth: str = "basic",
                       include_images: bool = False, **kwargs) -> Response:
        url_list = [u.strip() for u in str(urls or "").split(",") if u.strip()]
        if not url_list:
            return self._fail(f"{self.id}: 'urls' (comma-separated) is required.")
        key = self._secret(api_key, "TAVILY_API_KEY")
        if not key:
            return self._fail(f"{self.id}: no API key (set api_key or TAVILY_API_KEY).")
        try:
            # Extract authenticates with a bearer header, unlike search's body key.
            body = await self.owner.post(
                "/extract",
                {"urls": url_list, "extract_depth": extract_depth, "include_images": include_images},
                bearer=key,
            )
        except Exception as exc:  # noqa: BLE001 — network / auth / quota
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        records = [{"url": r.get("url"), "raw_content": r.get("raw_content", ""),
                    "images": r.get("images", [])} for r in body.get("results", [])]
        return self._ok(f"Extracted content from {len(records)} URL(s).",
                        records=records, failed=body.get("failed_results", []), count=len(records))
