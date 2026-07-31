"""Firecrawl search — web search with scraped markdown content via Firecrawl API."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ConfigDict, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from autogenesis.logger import logger
from autogenesis.registry import TOOL
from autogenesis.tool.default.search.types import SearchItem
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.utils import hvac_client

def _is_retryable(exc: BaseException) -> bool:
    """Retry on network errors and 5xx only; 4xx are not retryable."""
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True,
)
async def _make_firecrawl_request(
    payload: Dict[str, Any], headers: Dict[str, str], api_base: str
) -> httpx.Response:
    """Make HTTP request to Firecrawl search API with retry logic."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_base}/search",
            json=payload,
            headers=headers,
            timeout=httpx.Timeout(60.0),
        )
        response.raise_for_status()
        return response


_DESCRIPTION = "Search the web via Firecrawl API, prioritising research papers and PDFs."

_INSTRUCTION = """
## Function
Search the web via Firecrawl API, prioritising research papers and PDFs.

## Guidance
- Returns results with full scraped markdown content.

## Parameters
- query (str): The search query string.
- image (str, optional): Unused image path argument (default: None).
- num_results (int, optional): Number of results to return (default: 10).
- filter_year (int, optional): Filter results by year (default: None).

## Example
{"name": "firecrawl_search_tool", "args": {"query": "transformer architecture survey", "num_results": 5}}
"""


@TOOL.register_module(force=True)
class FirecrawlSearch(Tool):
    """Web search with scraped markdown content via Firecrawl API.

    Uses the /search endpoint with research and PDF category filtering,
    and returns full markdown content for each result.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "firecrawl_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    api_key: str = Field(default="", description="Firecrawl API key")
    api_base: str = Field(default="", description="Firecrawl API base URL")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = hvac_client.get("FIRECRAWL_API_KEY") or ""
        self.api_base = hvac_client.get("FIRECRAWL_API_BASE") or "https://api.firecrawl.dev/v2"

    async def __call__(
        self,
        query: str,
        image: Optional[str] = None,
        num_results: Optional[int] = 10,
        filter_year: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Execute a web search via Firecrawl API.

        Args:
            query: The search query string.
            num_results: Number of results to return (default: 10).
            filter_year: Filter results by year.
        """
        if not self.api_key:
            return Response(type=ResponseType.TOOL, 
                success=False,
                message="FIRECRAWL_API_KEY not set",
            )

        if not query or not query.strip():
            return Response(type=ResponseType.TOOL, 
                success=False,
                message="Search query cannot be empty",
            )

        try:
            payload: Dict[str, Any] = {
                "query": query.strip(),
                "limit": num_results or 10,
                "categories": ["research", "pdf"],
            }


            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            response = await _make_firecrawl_request(payload, headers, self.api_base)
            data = response.json()

            if not data.get("success"):
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=f"Firecrawl search returned unsuccessful response: {data}",
                )

            raw_results: List[Dict[str, Any]] = data.get("data", {}).get("web", [])

            search_items: List[SearchItem] = []

            for i, item in enumerate(raw_results):
                url = item.get("url", "")
                title = item.get("title", "") or item.get("metadata", {}).get("title", "")
                description = item.get("description", "") or item.get("metadata", {}).get("description", "")

                search_items.append(
                    SearchItem(
                        title=title,
                        url=url,
                        description=description,
                        position=i + 1,
                        source="firecrawl",
                    )
                )

            if not search_items:
                return Response(type=ResponseType.TOOL, 
                    success=True,
                    message=f"No search results found for: {query}",
                    data={
                        "query": query,
                        "num_results": 0,
                        "search_items": [],
                        "engine": "firecrawl",
                    },
                )

            results_json = json.dumps(
                [
                    {
                        "title": item.title,
                        "url": item.url,
                        "description": item.description or "",
                        "position": item.position,
                        "content": item.content or "",
                    }
                    for item in search_items
                ],
                ensure_ascii=False,
                indent=4,
            )

            message = f"Firecrawl search results for query: {query}\n\n{results_json}"

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                data={
                    "query": query,
                    "num_results": len(search_items),
                    "search_items": search_items,
                    "engine": "firecrawl",
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"| Firecrawl search HTTP error: {e.response.status_code} — {e.response.text}")
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Firecrawl search failed: HTTP {e.response.status_code} — {e.response.text}",
            )
        except Exception as e:
            logger.error(f"| Firecrawl search error: {e}")
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Firecrawl search failed: {str(e)}",
            )
