"""Web fetcher tool for retrieving content from web pages."""

from pydantic import Field
from typing import Dict, Any

from autogenesis.utils import fetch_url
from autogenesis.logger import logger
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Visit a webpage at a given URL and return its text content."

_INSTRUCTION = """
## Function
Visit a webpage at a given URL and return its text content.

## Guidance
- Use this tool to fetch and read content from web pages.
- The tool will return the page title and markdown-formatted content.

## Parameters
- url (str): The URL of the webpage to fetch.

## Example
{"name": "web_fetcher_tool", "args": {"url": "https://www.google.com"}}
"""

@TOOL.register_module(force=True)
class WebFetcherTool(Tool):
    """A tool for fetching web content asynchronously."""

    name: str = "web_fetcher_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    
    def __init__(self, enable_evolving: bool = False, **kwargs):
        """A tool for fetching web content asynchronously."""
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, url: str, **kwargs) -> Response:
        """
        Fetch content from a given URL asynchronously.

        Args:
            url (str): The relative or absolute URL of the webpage to visit.
        """
        try:
            res = await fetch_url(url)
            if not res:
                logger.error(f"Failed to fetch content from {url}")
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=f"Failed to fetch content from {url}",
                    data={"url": url, "status": "failed"}
                )
            title = res.get("title", "")
            markdown = res.get("markdown", "")
            formatted = f"Title: {title}\nContent: {markdown}"
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=formatted,
                data={
                    "url": url,
                    "status": "success",
                    "content_length": len(formatted),
                    "title": title,
                    "markdown_length": len(markdown) if markdown else 0
                }
            )
        except Exception as e:
            logger.error(f"Error fetching content: {e}")
            return Response(type=ResponseType.TOOL, 
                success=False,
                message=f"Failed to fetch content: {e}",
                data={
                    "url": url,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
