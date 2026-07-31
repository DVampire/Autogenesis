"""Data-source tools for the canvas Data category.

``http_request_tool`` makes a plain REST call, opting into a standalone canvas node via
``metadata["canvas_category"] = "data"``.
"""

import json as _json
from typing import Any, Dict, Optional

from pydantic import Field

from autogenesis.registry import TOOL
from autogenesis.response.types import Response, ResponseType
from autogenesis.tool.types import Tool


@TOOL.register_module(force=True)
class HttpRequestTool(Tool):
    """Make an HTTP request and return status, headers, and parsed body."""

    name: str = "http_request_tool"
    description: str = "Make an HTTP request (GET/POST/PUT/DELETE) to a URL and return the status and body."
    instruction: str = (
        "## Function\nCall a REST endpoint and return the response.\n\n"
        "## Parameters\n- url (str): the request URL.\n- method (str): GET (default) / POST / PUT / DELETE / PATCH.\n"
        "- headers (object): optional request headers.\n- body (str): optional request body (JSON or text).\n\n"
        "## Example\n{\"name\": \"http_request_tool\", \"args\": {\"url\": \"https://api.example.com/x\", \"method\": \"GET\"}}"
    )
    metadata: Dict[str, Any] = Field(default={"canvas_category": "data"})
    permission_mode: str = "read_only"

    async def __call__(self, url: str, method: str = "GET", headers: Optional[Dict[str, Any]] = None,
                       body: str = "", timeout: float = 30.0, **kwargs) -> Response:
        import httpx

        method = str(method or "GET").upper()
        request_kwargs: Dict[str, Any] = {"headers": headers or None}
        if body:
            content = body
            if isinstance(body, (dict, list)):
                content = _json.dumps(body)
            request_kwargs["content"] = content
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(method, str(url), **request_kwargs)
        except Exception as exc:  # noqa: BLE001 — network errors are a failed result
            return Response(type=ResponseType.TOOL, success=False, message=f"Request failed: {exc}")
        try:
            parsed = response.json()
        except (ValueError, TypeError):
            parsed = response.text
        ok = response.status_code < 400
        message = response.text if isinstance(parsed, str) else _json.dumps(parsed, ensure_ascii=False)
        return Response(
            type=ResponseType.TOOL, success=ok,
            message=message if ok else f"HTTP {response.status_code}: {message[:500]}",
            data={"status": response.status_code, "body": parsed, "headers": dict(response.headers)},
        )
