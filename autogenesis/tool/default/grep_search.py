"""GrepSearchTool — search file contents for a pattern."""

import os
import re
from typing import Any, Dict, List, Optional

from pydantic import Field

from autogenesis.registry import TOOL
from autogenesis.sandbox.project import check_session_path
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType

_IGNORED_DIRS = frozenset({
    ".git", "node_modules", "target", "dist", "build",
    "coverage", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache",
})

_DESCRIPTION = "Search file contents for lines matching a regex or literal string."

_INSTRUCTION = """
## Function
Search file contents for lines matching a regex or literal string.

## Guidance
- Only files whose names match file_pattern are searched; common noise directories (.git, node_modules, __pycache__, .venv, etc.) are skipped automatically.
- An invalid regex pattern returns an error rather than matches.
- Results are capped at max_results; each match reports the file path, line number, and line text.

## Parameters
- pattern (str): Regular expression (or literal string) to search for.
- root (str): Absolute path to the directory to search in.
- file_pattern (str, optional): Glob pattern to filter which files are searched, e.g. "*.py". Defaults to all files.
- case_sensitive (bool, optional): Whether the search is case-sensitive. Defaults to true.
- max_results (int, optional): Maximum number of matching lines to return. Defaults to 100.

## Example
{"name": "grep_search_tool", "args": {"pattern": "def __call__", "root": "/abs/path/to/project", "file_pattern": "*.py"}}
"""


@TOOL.register_module(force=True)
class GrepSearchTool(Tool):
    """Search file contents for regex/literal matches, skipping common noise directories."""

    name: str = "grep_search_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={"canvas_category": "files"})
    enable_evolving: bool = Field(default=False)

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(
        self,
        pattern: str,
        root: str,
        file_pattern: str = "*",
        case_sensitive: bool = True,
        max_results: int = 100,
        **kwargs,
    ) -> Response:
        """Search file contents for pattern.

        Args:
            pattern:        Regex pattern to search.
            root:           Absolute directory to search.
            file_pattern:   Glob filter for filenames.
            case_sensitive: Case-sensitive matching.
            max_results:    Cap on returned matches.
        """
        try:
            sandbox_denial = check_session_path(kwargs.get("ctx"), root, write=False)
            if sandbox_denial:
                return Response(type=ResponseType.TOOL, success=False, message=sandbox_denial)
            if not os.path.isdir(root):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: Not a directory: {root}")

            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                compiled = re.compile(pattern, flags)
            except re.error as e:
                return Response(type=ResponseType.TOOL, success=False, message=f"Invalid regex pattern: {e}")

            from fnmatch import fnmatch

            results: List[Dict[str, Any]] = []

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]

                for filename in filenames:
                    if not fnmatch(filename, file_pattern):
                        continue

                    full = os.path.join(dirpath, filename)
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as f:
                            for lineno, line in enumerate(f, 1):
                                if compiled.search(line):
                                    results.append({
                                        "file": full,
                                        "line": lineno,
                                        "text": line.rstrip("\n"),
                                    })
                                    if len(results) >= max_results:
                                        break
                    except OSError:
                        continue

                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

            truncated = len(results) >= max_results

            if not results:
                message = f"No matches found for '{pattern}' under {root}"
            else:
                lines = "\n".join(
                    f"{r['file']}:{r['line']}: {r['text']}" for r in results
                )
                suffix = f"\n[Results capped at {max_results}.]" if truncated else ""
                message = f"Found {len(results)} match(es):\n{lines}{suffix}"

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                data={"results": results, "truncated": truncated, "pattern": pattern},
            )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error in grep search: {e}")
