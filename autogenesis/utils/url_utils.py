import os
import asyncio
from typing import Dict, Any
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv(verbose=True)

import aiohttp

# Default timeout for web fetching (in seconds)
DEFAULT_FETCH_TIMEOUT = 15  # 15 seconds per fetch attempt

async def jina_fetch_url(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT):
    """Fetch content using Jina AI Reader (r.jina.ai) with timeout."""
    try:
        from autogenesis.utils.hvac_utils import hvac_client

        safe_chars = ":/?#[]@!$&'()*+,;="

        base_url = hvac_client.get("JINA_BASE_URL")
        api_key = hvac_client.get("JINA_API_KEY")

        reader_url = f"{base_url}/{quote(url, safe=safe_chars)}"
        headers = {
            "X-MiroAPI-Batch-Id": "123",
            "X-MiroAPI-Trace-Id": "trace123",
            "X-With-Iframe": "true",
            "X-No-Cache": "true"
        }
        
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            response = await asyncio.wait_for(
                session.get(reader_url, headers=headers),
                timeout=timeout,
            )
            async with response as resp:
                resp.raise_for_status()
                return await resp.text()
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


async def fetch_crawl4ai_url(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT):
    """Fetch content from a given URL using the crawl4ai library with timeout."""
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            # Wrap the arun call with timeout
            response = await asyncio.wait_for(
                crawler.arun(url=url),
                timeout=timeout
            )

            if response:
                result = response.markdown
                return result
            else:
                return None
    except asyncio.TimeoutError:
        return None
    except Exception as e:
        return None

async def firecrawl_fetch_url(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT):
    """Fetch content using Firecrawl scrape API with timeout."""
    try:
        from autogenesis.utils.hvac_utils import hvac_client

        api_base = hvac_client.get("FIRECRAWL_API_BASE") or "https://api.firecrawl.dev/v2"
        api_key = hvac_client.get("FIRECRAWL_API_KEY")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "url": url, 
            "formats": ["markdown"],
            "max_age": 7 * 24 * 3600,  # 7 days
        }

        async with aiohttp.ClientSession() as session:
            response = await asyncio.wait_for(
                session.post(f"{api_base}/scrape", json=payload, headers=headers),
                timeout=timeout,
            )
            async with response as resp:
                resp.raise_for_status()
                data = await resp.json()
                if data.get("success"):
                    return data.get("data", {}).get("markdown")
                return None
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


async def fetch_url(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT) -> Dict[str, Any]:
    """Fetch content from a URL using Jina Reader and Crawl4AI with timeout.

    Args:
        url: The URL to fetch
        timeout: Timeout in seconds for each fetch attempt (default: 15)

    Returns:
        DocumentConverterResult if successful, None otherwise
    """

    try:
        # Try Firecrawl first
        firecrawl_result = await firecrawl_fetch_url(url, timeout=timeout)
        if firecrawl_result:
            return {
                "markdown": firecrawl_result,
                "title": f"Fetched content from {url} using Firecrawl",
            }

        # Fallback to Jina Reader
        jina_result = await jina_fetch_url(url, timeout=timeout)
        if jina_result:
            return {
                "markdown": jina_result,
                "title": f"Fetched content from {url} using Jina Reader",
            }

        # Fallback to Crawl4AI
        crawl4ai_result = await fetch_crawl4ai_url(url, timeout=timeout)
        if crawl4ai_result:
            return {
                "markdown": crawl4ai_result,
                "title": f"Fetched content from {url} using Crawl4AI",
            }
    except Exception as e:
        return None

    return None

if __name__ == '__main__':
    import asyncio
    url = "https://www.google.com/"
    result = asyncio.run(fetch_url(url))
    print(result)
