"""GitExtractor."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class GitextractorTool(PluginTool):
    """GitExtractor."""

    name: str = 'gitextractor'
    display_name: str = 'GitExtractor'
    description: str = 'Analyzes a Git repository and returns file contents and complete repository information'

    async def __call__(self, clone_url: str = "", branch: str = "main", **kwargs) -> Response:
        import tempfile
        if not clone_url:
            return self._fail("gitextractor: 'clone_url' is required.")
        try:
            from langchain_community.document_loaders.git import GitLoader
            docs = GitLoader(repo_path=tempfile.mkdtemp(), clone_url=clone_url, branch=branch).load()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"gitextractor: {type(exc).__name__}: {exc}")
        text = "\n\n".join(f"# {d.metadata.get('file_path','')}\n{d.page_content}" for d in docs)
        return self._ok(f"Extracted {len(docs)} files ({len(text)} chars).", text=text, files=len(docs))
