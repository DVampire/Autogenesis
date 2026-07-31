from __future__ import annotations
from typing import Any, Optional, Dict, List
import json
import aiohttp
from urllib.parse import quote
from pydantic import ConfigDict, Field
from dotenv import load_dotenv
load_dotenv()

from autogenesis.tool.default.search.types import SearchItem
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL
from autogenesis.utils import hvac_client


_DESCRIPTION = "A search engine powered by Jina AI."

_INSTRUCTION = """
## Function
A search engine powered by Jina AI.

## Guidance
- Useful for when you need to answer questions about current events.
- Input should be a search query.

## Parameters
- query (str): The query to search for.
- image (str, optional): Unused image path argument (default: None).
- num_results (int, optional): The number of search results to return (default: 5).
- country (str, optional): The country to search in (default: 'us').
- lang (str, optional): The language to search in (default: 'en').
- filter_year (int, optional): The year to filter results by (default: None).

## Example
{"name": "jina_search_tool", "args": {"query": "latest space missions 2026", "num_results": 5}}
"""


@TOOL.register_module(force=True)
class JinaSearch(Tool):
    """Tool that queries the Jina AI search engine.

    Example usages:
    .. code-block:: python
        # basic usage
        tool = JinaSearch()
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "jina_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    api_key: str = Field(default="", description="Jina AI API key")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = hvac_client.get("JINA_API_KEY") or ""

    async def _search_jina(
        self,
        query: str,
        num_results: int = 10,
    ) -> List[SearchItem]:
        """
        Perform a Jina AI search using the provided parameters.
        Returns a list of SearchItem objects.
        """
        results = []

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"https://s.jina.ai/{quote(query)}"
        params = {"count": num_results}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    resp.raise_for_status()
                    response_data = await resp.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"Jina search HTTP error: {e.status} {e.message}")
            return results
        except Exception as e:
            logger.error(f"Jina search API call failed: {e}")
            return results

        if response_data is None:
            logger.warning("Jina search returned None response")
            return results

        logger.debug(f"Jina search response type: {type(response_data)}")

        # Response format: {"code": 200, "data": [...]}
        raw_items = None
        if isinstance(response_data, dict):
            raw_items = response_data.get("data") or response_data.get("results") or []
        elif isinstance(response_data, list):
            raw_items = response_data

        if not raw_items:
            logger.warning(f"Jina search returned no results. Response: {str(response_data)}")
            return results

        for item in raw_items:
            if item is None:
                continue

            if isinstance(item, dict):
                title = item.get("title", "") or ""
                url_val = item.get("url", "") or ""
                description = item.get("description", "") or item.get("content", "") or ""
                date = item.get("date", None)
            else:
                title = getattr(item, "title", None) or ""
                url_val = getattr(item, "url", None) or ""
                description = getattr(item, "description", None) or getattr(item, "content", None) or ""
                date = getattr(item, "date", None)

            if url_val:
                results.append(SearchItem(
                    title=title,
                    url=url_val,
                    description=description,
                    date=date,
                ))

        return results

    async def __call__(
        self,
        query: str,
        image: Optional[str] = None,
        num_results: Optional[int] = 5,
        country: Optional[str] = "us",
        lang: Optional[str] = "en",
        filter_year: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """
        Jina AI search tool.

        Args:
            query (str): The query to search for.
            num_results (Optional[int]): The number of search results to return.
            country (Optional[str]): The country to search in.
            lang (Optional[str]): The language to search in.
            filter_year (Optional[int]): The year to filter results by.
        """
        try:
            search_items = await self._search_jina(query, num_results=num_results)

            results_json = json.dumps([{
                "title": item.title,
                "url": item.url,
                "description": item.description or "",
                "date": item.date or "",
            } for item in search_items], ensure_ascii=False, indent=4)

            message = f"Jina search results for query: {query}\n\n{results_json}"

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                data={
                    "query": query,
                    "num_results": len(search_items),
                    "search_items": search_items,
                    "engine": "jina",
                }
            )

        except Exception as e:
            logger.error(f"Error in Jina search: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Error in Jina search: {str(e)}")
