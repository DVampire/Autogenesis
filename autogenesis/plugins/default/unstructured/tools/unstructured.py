"""Unstructured API."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class UnstructuredTool(PluginTool):
    """Unstructured API."""

    name: str = 'unstructured'
    display_name: str = 'Unstructured API'
    description: str = ''

    async def __call__(self, file_path: str = "", api_key: str = "", api_url: str = "", **kwargs) -> Response:
        key = self._secret(api_key, "UNSTRUCTURED_API_KEY")
        if not file_path:
            return self._fail("unstructured: 'file_path' is required.")
        try:
            from langchain_unstructured import UnstructuredLoader
            kw = {"file_path": file_path}
            if key:
                kw["api_key"] = key
                kw["url"] = api_url or "https://api.unstructuredapp.io/general/v0/general"
                kw["partition_via_api"] = True
            docs = UnstructuredLoader(**kw).load()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"unstructured: {type(exc).__name__}: {exc}")
        records = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
        return self._ok(f"Parsed {len(records)} elements from the file.", records=records, count=len(records))
