"""media_search tool — find REAL images by keyword and download them locally.

A shopping site (or any UI) needs real, attractive imagery. Hotlinking an external
CDN is fragile (breaks when the host is blocked/offline) and hand-drawn inline-SVG
placeholders look generic. This tool bridges the gap: it searches a keyless image
provider (Openverse — Creative-Commons media, no API key) by keyword, DOWNLOADS the
top results into a local directory, and returns their on-disk paths. The caller can
then bundle those files into the project so the result is BOTH real-looking AND
self-contained (no runtime dependency on an external host).
"""

import os
import re
import json
import mimetypes
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Search for REAL images by keyword and download them to a local folder (keyless, via Openverse) so they can be bundled into a project — real-looking AND self-contained."

_INSTRUCTION = """
## Function
Search a keyless image provider (Openverse, Creative-Commons) by keyword and DOWNLOAD the top matches into a local directory. Returns the saved file paths so you can bundle real images into your project (e.g. a product catalog) instead of hotlinking a fragile CDN or drawing placeholder SVGs.

## Parameters
- query (str, required): what to find, e.g. "wireless headphones", "ceramic coffee mug".
- out_dir (str, required): absolute directory to save images into (created if missing), e.g. the project's `src/assets/products/`.
- count (int, optional): how many images to download (default 3, max 10).
- name_prefix (str, optional): base filename for saved images (default derived from query); files are `<prefix>-<i>.<ext>`.
- media_type (str, optional): "image" (default). Video search is not yet supported.

## Returns (message + data.items)
For each downloaded image: `local_path` (use this in your code), `source_url`, `title`, `creator`, `license`. Failed downloads are skipped and reported.

## Guidance
- Save into a folder INSIDE your project's source (e.g. `src/assets/...`) so the bundler picks them up and the deployed site is self-contained.
- Import/reference the returned `local_path`s from your components; do NOT hotlink the original `source_url` at runtime (that reintroduces the fragile-external-image problem).
- Attribution: images are Creative-Commons; keep the returned creator/license if you show credits.

## Example
{"name": "media_search_tool", "args": {"query": "wireless headphones", "out_dir": "/abs/path/online_shop/src/assets/products", "count": 3, "name_prefix": "headphones"}}
"""

_OPENVERSE_ENDPOINT = "https://api.openverse.org/v1/images/"
_UA = "Autogenesis-media-search/1.0 (+https://example.local)"


def _slugify(text: str) -> str:
    """Turn arbitrary text into a filesystem-safe, hyphenated slug.

    Non-alphanumeric runs collapse to single hyphens; empty results fall back to
    "image" so downloaded files always get a usable name.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "image"


def _ext_for(url: str, content_type: str) -> str:
    """Pick a safe image file extension for a downloaded asset.

    Prefers a known image extension from the URL path, then one guessed from the
    Content-Type header, and defaults to ".jpg" when neither is a recognized
    image type.
    """
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return ext
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip() or "")
    if guessed in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return guessed
    return ".jpg"


def _search_openverse(query: str, count: int) -> List[Dict[str, Any]]:
    """Query Openverse; return a list of result dicts (url/title/creator/license)."""
    params = urllib.parse.urlencode({"q": query, "page_size": max(1, min(count * 2, 20))})
    req = urllib.request.Request(f"{_OPENVERSE_ENDPOINT}?{params}", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("results", []) or []


def _download(url: str, dest: str) -> None:
    """Download the bytes at `url` and write them to the local path `dest`.

    Sends the module User-Agent and reads the whole response into memory before
    writing (suitable for images, not large files).
    """
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = resp.read()
    with open(dest, "wb") as fh:
        fh.write(data)


@TOOL.register_module(force=True)
class MediaSearchTool(Tool):
    """Search + download real images by keyword (keyless, Openverse) for local bundling."""

    name: str = "media_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Downloads image files into a local directory.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, query: str, out_dir: str, count: int = 3,
                       name_prefix: str = "", media_type: str = "image", **kwargs) -> Response:
        import asyncio

        if media_type != "image":
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"media_type={media_type!r} not supported yet (only 'image').")
        if not query or not out_dir:
            return Response(type=ResponseType.TOOL, success=False,
                            message="query and out_dir are required.")
        count = max(1, min(int(count), 10))
        prefix = _slugify(name_prefix or query)
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"cannot create out_dir: {e}")

        try:
            results = await asyncio.to_thread(_search_openverse, query, count)
        except Exception as e:
            logger.error(f"| ❌ media_search: openverse query failed: {e}")
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"image search failed for {query!r}: {e}")
        if not results:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"no images found for {query!r}.")

        items: List[Dict[str, Any]] = []
        errors: List[str] = []
        for r in results:
            if len(items) >= count:
                break
            url = r.get("url")
            if not url:
                continue
            dest = os.path.join(out_dir, f"{prefix}-{len(items) + 1}{_ext_for(url, '')}")
            try:
                await asyncio.to_thread(_download, url, dest)
            except Exception as e:
                errors.append(f"{url}: {e}")
                continue
            if os.path.getsize(dest) < 512:  # too small to be a real image
                try:
                    os.remove(dest)
                except Exception:
                    pass
                errors.append(f"{url}: too small / not an image")
                continue
            items.append({
                "local_path": dest,
                "source_url": url,
                "title": r.get("title", ""),
                "creator": r.get("creator", ""),
                "license": r.get("license", ""),
            })

        if not items:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"found matches for {query!r} but all downloads failed: {errors[:3]}")

        lines = [f"# media_search {query!r} → {len(items)} image(s) saved to {out_dir}"]
        for it in items:
            lines.append(f"- {it['local_path']}  (from {it['source_url']}, {it['license'] or 'cc'})")
        if errors:
            lines.append(f"({len(errors)} skipped)")
        lines.append("Reference the local_path values in your code; do NOT hotlink source_url at runtime.")
        return Response(type=ResponseType.TOOL, success=True, message="\n".join(lines),
                        data={"items": items, "count": len(items), "skipped": errors})
