"""ReadFileTool — read file contents with optional line range."""

import os
from typing import Any, Dict, Optional

from pydantic import Field

from autogenesis.permission import Operation, PermissionRequest, permission_manager
from autogenesis.registry import TOOL
from autogenesis.config import config
from autogenesis.sandbox.project import check_session_path
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType

_DESCRIPTION = "Read the contents of a file."

_INSTRUCTION = """
## Function
Read the contents of a file.

## Guidance
- Returns the file content with line numbers prefixed.
- By default the whole file is read; use offset/limit to read a specific line range.

## Parameters
- path (str): Absolute path to the file to read.
- offset (int, optional): Line number to start reading from (1-based). Defaults to 1.
- limit (int, optional): Maximum number of lines to read. Defaults to the whole file.

## Example
{"name": "read_file_tool", "args": {"path": "/abs/path/to/file.py"}}
{"name": "read_file_tool", "args": {"path": "/abs/path/to/file.py", "offset": 50, "limit": 100}}
"""


@TOOL.register_module(force=True)
class ReadFileTool(Tool):
    """Read file contents with optional line range, returning numbered lines."""

    name: str = "read_file_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={"canvas_category": "files"})
    enable_evolving: bool = Field(default=False)
    progress_policy: str = "workspace"

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(
        self,
        path: str,
        offset: int = 1,
        limit: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Read file contents with line numbers.

        Args:
            path:   Absolute path to the file.
            offset: First line to return (1-based).
            limit:  Maximum number of lines to return. None reads to end of file.
        """
        try:
            # A peer sandbox bound on the context routes file IO into that container
            # (e.g. a programbench task cleanroom); otherwise read the local fs, which
            # under Model X already IS the project container.
            sandbox = (getattr(kwargs.get("ctx"), "extra", None) or {}).get("sandbox")

            # The host-root boundary check only applies to local reads: with a peer
            # bound, the container itself is the isolation boundary and paths (e.g.
            # /workspace) live in the peer, not under the host session roots.
            if sandbox is None:
                sandbox_denial = check_session_path(kwargs.get("ctx"), path, write=False)
                if sandbox_denial:
                    return Response(type=ResponseType.TOOL, success=False, message=sandbox_denial)

            warning = ""
            if sandbox is not None:
                try:
                    content = await sandbox.read_file(path)
                except Exception as e:  # noqa: BLE001
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: cannot read {path} in sandbox: {e}")
                all_lines = content.splitlines(keepends=True)
            else:
                if not os.path.exists(path):
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: File not found: {path}")
                if not os.path.isfile(path):
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: Path is not a file: {path}")

                # Permission + guard check (size, binary)
                result = permission_manager.check(
                    self.name,
                    PermissionRequest(op=Operation.READ, target=path),
                    workspace=(config.workspace_root or ""),
                )
                if not result.allowed:
                    return Response(type=ResponseType.TOOL, success=False, message=f"Permission denied: {result.reason}")
                warning = result.warning or ""

                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()

            total_lines = len(all_lines)
            start = max(0, offset - 1)
            end = total_lines if limit is None else min(start + limit, total_lines)
            selected = all_lines[start:end]

            numbered = "".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))

            # Only note when the caller explicitly limited the range (not a default full read).
            truncation_note = ""
            if limit is not None and end < total_lines:
                truncation_note = (
                    f"\n[Showing lines {start+1}–{end} of {total_lines}. "
                    f"Use offset/limit to read more.]"
                )

            warning_prefix = f"Warning: {warning}\n\n" if warning else ""

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=warning_prefix + numbered + truncation_note,
                files=[path],
                data={"total_lines": total_lines, "start": start + 1, "end": end},
            )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error reading file: {e}")
