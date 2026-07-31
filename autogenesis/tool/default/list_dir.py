"""ListDirTool — list directory contents as a tree."""

import os
from typing import Dict, Any, List, Optional
from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL
from autogenesis.config import config
from autogenesis.sandbox.project import check_session_path

_DESCRIPTION = "List the contents of a directory as a tree structure."

_INSTRUCTION = """
## Function
List the contents of a directory as a tree structure.

## Guidance
- Directories are listed before files and results are rendered as an indented tree.
- Common noise directories (e.g. .git, __pycache__, node_modules) are ignored by default; add more via the ignore parameter.

## Parameters
- path (str): Absolute path to the directory to list.
- depth (int, optional): Maximum depth of the tree. Defaults to 3.
- ignore (list[str], optional): Directory/file name patterns to ignore. Defaults to common noise dirs like .git, __pycache__, node_modules.

## Example
{"name": "list_dir_tool", "args": {"path": "/abs/path/to/project"}}
{"name": "list_dir_tool", "args": {"path": "/abs/path/to/project", "depth": 2, "ignore": [".git", "node_modules"]}}
"""

_DEFAULT_IGNORE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    "*.pyc", "*.pyo", ".DS_Store",
}


@TOOL.register_module(force=True)
class ListDirTool(Tool):
    """List directory contents as a readable tree."""

    name: str = "list_dir_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={"canvas_category": "files"})
    enable_evolving: bool = Field(default=False)

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    def _should_ignore(self, name: str, ignore: set) -> bool:
        """Return True if an entry name should be excluded from the tree.

        Matches either an exact name in `ignore` or a simple `*suffix` glob
        pattern (e.g. "*.pyc").
        """
        if name in ignore:
            return True
        for pattern in ignore:
            if pattern.startswith("*") and name.endswith(pattern[1:]):
                return True
        return False

    def _build_tree(
        self,
        path: str,
        ignore: set,
        depth: int,
        current_depth: int,
        prefix: str,
        lines: List[str],
        file_count: List[int],
    ) -> None:
        """Recursively render a directory into an ASCII tree, in place.

        Walks `path` up to `depth` levels, appending formatted lines (with box-drawing
        connectors) to `lines` and incrementing the file tally. Directories are listed
        before files and symlinked directories are not followed.

        Args:
            path: Directory to scan at this level.
            ignore: Names/patterns to skip (see `_should_ignore`).
            depth: Maximum recursion depth allowed.
            current_depth: Depth of the current call (recursion stops beyond `depth`).
            prefix: Accumulated indentation prefix for this level.
            lines: Output accumulator, mutated in place.
            file_count: Single-element list used as a mutable file counter.
        """
        if current_depth > depth:
            return

        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[Permission denied]")
            return

        visible = [e for e in entries if not self._should_ignore(e.name, ignore)]

        for i, entry in enumerate(visible):
            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir(follow_symlinks=False):
                lines.append(f"{prefix}{connector}{entry.name}/")
                self._build_tree(
                    entry.path, ignore, depth, current_depth + 1,
                    child_prefix, lines, file_count,
                )
            else:
                lines.append(f"{prefix}{connector}{entry.name}")
                file_count[0] += 1

    async def __call__(
        self,
        path: str,
        depth: int = 3,
        ignore: Optional[List[str]] = None,
        **kwargs,
    ) -> Response:
        """List directory as a tree.

        Args:
            path: Absolute path to the directory.
            depth: Maximum recursion depth.
            ignore: Names/patterns to skip.
        """
        try:
            # A peer sandbox bound on the context lists inside that container (a flat
            # find listing); otherwise walk the local fs as a formatted tree.
            sandbox = (getattr(kwargs.get("ctx"), "extra", None) or {}).get("sandbox")

            # The host-root boundary check only applies to local listings: with a peer
            # bound, the container itself is the isolation boundary and paths (e.g.
            # /workspace) live in the peer, not under the host session roots.
            if sandbox is None:
                sandbox_denial = check_session_path(kwargs.get("ctx"), path, write=False)
                if sandbox_denial:
                    return Response(type=ResponseType.TOOL, success=False, message=sandbox_denial)

            if sandbox is not None:
                import shlex
                res = await sandbox.run_command(
                    f"find {shlex.quote(path)} -maxdepth {int(depth)} 2>/dev/null | sort"
                )
                if not res.success:
                    return Response(type=ResponseType.TOOL, success=False,
                                    message=f"Error listing {path} in sandbox: {res.as_message()}")
                listing = res.stdout.strip() or "(empty)"
                return Response(type=ResponseType.TOOL, success=True, message=listing,
                                data={"depth": depth, "sandboxed": True})

            if not os.path.exists(path):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: Path not found: {path}")
            if not os.path.isdir(path):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: Path is not a directory: {path}")

            ignore_set = _DEFAULT_IGNORE.copy()
            if ignore:
                ignore_set.update(ignore)

            lines = [f"{path}/"]
            file_count = [0]
            self._build_tree(path, ignore_set, depth, 1, "", lines, file_count)

            return Response(type=ResponseType.TOOL, 
                success=True,
                message="\n".join(lines),
                data={"file_count": file_count[0], "depth": depth},
            )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error listing directory: {e}")
