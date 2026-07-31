"""Serper API search engine — Google search via Serper.dev.

References MiroFlow's serper_search.py implementation:
- Serper API with retry logic
- HuggingFace URL filtering
- Quote-removal retry on empty results
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

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


def _is_huggingface_dataset_or_space_url(url: str) -> bool:
    """Filter out HuggingFace dataset/space URLs to prevent data leakage."""
    if not url:
        return False
    return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url


def _decode_urls_in_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Decode percent-encoded URLs in search results."""
    for item in results:
        if "link" in item and isinstance(item["link"], str):
            item["link"] = unquote(item["link"])
    return results


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
    ),
)
async def _make_serper_request(
    payload: Dict[str, Any], headers: Dict[str, str], base_url: str
) -> httpx.Response:
    """Make HTTP request to Serper API with retry logic."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/search",
            json=payload,
            headers=headers,
            timeout=httpx.Timeout(30.0),
        )
        response.raise_for_status()
        return response


_DESCRIPTION = "Search Google via Serper API and return organic search results."

_INSTRUCTION = """
## Function
Search Google via Serper API and return organic search results.

## Guidance
- Returns organic search results with titles, URLs, and snippets.

## Parameters
- query (str): The search query string.
- image (str, optional): Unused image path argument (default: None).
- num_results (int, optional): Number of results to return (default: 10).
- country (str, optional): Region code in ISO 3166-1 alpha-2 format (default: 'us').
- lang (str, optional): Language code in ISO 639-1 format (default: 'en').
- filter_year (int, optional): Filter results by year (default: None).

## Example
{"name": "serper_search_tool", "args": {"query": "latest AI research", "num_results": 5}}
"""


@TOOL.register_module(force=True)
class SerperSearch(Tool):
    """Google search via Serper API.

    Mirrors MiroFlow's serper_search.py:
    - Organic results with HuggingFace filtering
    - Quote-removal retry when no results
    - tenacity retry with exponential backoff
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "serper_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    api_key: str = Field(default="", description="Serper API key")
    api_base: str = Field(default="", description="Serper API base URL")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = hvac_client.get("SERPER_API_KEY") or ""
        self.api_base = hvac_client.get("SERPER_BASE_URL") or "https://google.serper.dev"

    async def _perform_search(
        self,
        query: str,
        num_results: int = 10,
        gl: str = "us",
        hl: str = "en",
        tbs: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Perform a single search and return (organic_results, search_params)."""
        payload: Dict[str, Any] = {
            "q": query.strip(),
            "gl": gl,
            "hl": hl,
            "num": num_results,
        }
        if tbs:
            payload["tbs"] = tbs

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        response = await _make_serper_request(payload, headers, self.api_base)
        data = response.json()

        # Filter out HuggingFace dataset/space URLs
        organic_results = []
        if "organic" in data:
            for item in data["organic"]:
                if _is_huggingface_dataset_or_space_url(item.get("link", "")):
                    continue
                organic_results.append(item)

        return organic_results, data.get("searchParameters", {})

    async def __call__(
        self,
        query: str,
        image: Optional[str] = None,
        num_results: Optional[int] = 10,
        country: Optional[str] = "us",
        lang: Optional[str] = "en",
        filter_year: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Execute a Google search via Serper API.

        Args:
            query: The search query string.
            num_results: Number of results to return (default: 10).
            country: Region code in ISO 3166-1 alpha-2 format (default: 'us').
            lang: Language code in ISO 639-1 format (default: 'en').
            filter_year: Filter results by year (uses tbs parameter).
        """
        if not self.api_key:
            return Response(type=ResponseType.TOOL, 
                success=False,
                message="SERPER_API_KEY not set",
            )

        if not query or not query.strip():
            return Response(type=ResponseType.TOOL, 
                success=False,
                message="Search query cannot be empty",
            )

        try:
            # Build time-based search filter if year specified
            tbs = None
            if filter_year:
                tbs = f"cdr:1,cd_min:1/1/{filter_year},cd_max:12/31/{filter_year}"

            # Perform initial search
            original_query = query.strip()
            organic_results, search_params = await self._perform_search(
                original_query,
                num_results=num_results or 10,
                gl=country or "us",
                hl=lang or "en",
                tbs=tbs,
            )

            # If no results and query contains quotes, retry without quotes
            if not organic_results and '"' in original_query:
                query_without_quotes = original_query.replace('"', "").strip()
                if query_without_quotes:
                    logger.info(
                        f"| Serper: No results with quotes, retrying without: {query_without_quotes}"
                    )
                    organic_results, search_params = await self._perform_search(
                        query_without_quotes,
                        num_results=num_results or 10,
                        gl=country or "us",
                        hl=lang or "en",
                        tbs=tbs,
                    )

            # Decode URLs
            organic_results = _decode_urls_in_results(organic_results)

            # Convert to SearchItem list
            search_items = []
            for i, item in enumerate(organic_results):
                search_items.append(
                    SearchItem(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        description=item.get("snippet", ""),
                        position=item.get("position", i + 1),
                        source="serper",
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
                        "engine": "serper",
                    },
                )

            results_json = json.dumps(
                [
                    {
                        "title": item.title,
                        "url": item.url,
                        "description": item.description or "",
                        "position": item.position,
                    }
                    for item in search_items
                ],
                ensure_ascii=False,
                indent=4,
            )

            message = f"Serper search results for query: {query}\n\n{results_json}"

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                data={
                    "query": query,
                    "num_results": len(search_items),
                    "search_items": search_items,
                    "engine": "serper",
                },
            )

        except Exception as e:
            logger.error(f"| Serper search error: {e}")
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Serper search failed: {str(e)}",
            )
