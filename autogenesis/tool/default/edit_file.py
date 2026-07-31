"""EditFileTool — precise string-replace editing (Claude Code style)."""

import difflib
import os
from typing import Any, Dict, List

from pydantic import Field

from autogenesis.permission import Operation, PermissionRequest, is_binary_file, permission_manager
from autogenesis.registry import TOOL
from autogenesis.config import config
from autogenesis.sandbox.project import check_session_path
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType

_DESCRIPTION = "Edit a file by replacing an exact string with a new string."

_INSTRUCTION = """
## Function
Edit a file by replacing an exact string with a new string.

## Guidance
- The old_string must appear EXACTLY ONCE in the file. If it appears zero or more than once, the edit is rejected — add more surrounding context to make it unique.
- Use read_file_tool first to see the current file content before editing.

## Parameters
- path (str): Absolute path to the file to edit.
- old_string (str): The exact text to find and replace. Must be unique in the file.
- new_string (str): The text to replace it with. Use empty string "" to delete old_string.

## Example
{"name": "edit_file_tool", "args": {"path": "/abs/path/to/file.py", "old_string": "def foo():\\n    pass", "new_string": "def foo():\\n    return 42"}}
"""


@TOOL.register_module(force=True)
class EditFileTool(Tool):
    """Precise string-replace file editor. Requires old_string to be unique in the file."""

    name: str = "edit_file_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={"canvas_category": "files"})
    enable_evolving: bool = Field(default=False)

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(
        self,
        path: str,
        old_string: str,
        new_string: str,
        **kwargs,
    ) -> Response:
        """Replace old_string with new_string in the file at path.

        Args:
            path:       Absolute path to the file.
            old_string: Exact text to replace (must appear exactly once).
            new_string: Replacement text.
        """
        try:
            # A peer sandbox bound on the context routes the read-modify-write into
            # that container; otherwise operate on the local fs.
            sandbox = (getattr(kwargs.get("ctx"), "extra", None) or {}).get("sandbox")

            # The host-root boundary check only applies to local edits: with a peer
            # bound, the container itself is the isolation boundary and paths (e.g.
            # /workspace) live in the peer, not under the host session roots.
            if sandbox is None:
                sandbox_denial = check_session_path(kwargs.get("ctx"), path, write=True)
                if sandbox_denial:
                    return Response(type=ResponseType.TOOL, success=False, message=sandbox_denial)
                if not os.path.exists(path):
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: File not found: {path}")
                if not os.path.isfile(path):
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: Path is not a file: {path}")
                if is_binary_file(path):
                    return Response(type=ResponseType.TOOL, success=False, message="Error: Binary file — use a dedicated binary tool.")

            # Permission check (write op). With a peer bound the container is the
            # boundary, so pass workspace="" to skip the host-path check.
            result = permission_manager.check(
                self.name,
                PermissionRequest(op=Operation.WRITE, target=path, content=new_string),
                workspace=("" if sandbox is not None else (config.workspace_root or "")),
            )
            if not result.allowed:
                return Response(type=ResponseType.TOOL, success=False, message=f"Permission denied: {result.reason}")

            if sandbox is not None:
                try:
                    original = await sandbox.read_file(path)
                except Exception as e:  # noqa: BLE001
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: cannot read {path} in sandbox: {e}")
            else:
                with open(path, "r", encoding="utf-8") as f:
                    original = f.read()

            count = original.count(old_string)
            if count == 0:
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=(
                        "Error: old_string not found in file. "
                        "Use read_file_tool to verify the exact content before editing."
                    ),
                )
            if count > 1:
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=(
                        f"Error: old_string appears {count} times in the file. "
                        "Provide more surrounding context to make it unique."
                    ),
                )

            updated = original.replace(old_string, new_string, 1)

            if sandbox is not None:
                try:
                    await sandbox.write_file(path, updated)
                except Exception as e:  # noqa: BLE001
                    return Response(type=ResponseType.TOOL, success=False, message=f"Error: cannot write {path} in sandbox: {e}")
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(updated)

            # Build unified diff for extra.data
            orig_lines: List[str] = original.splitlines(keepends=True)
            upd_lines: List[str] = updated.splitlines(keepends=True)
            patch = list(difflib.unified_diff(
                orig_lines, upd_lines,
                fromfile=f"a/{os.path.basename(path)}",
                tofile=f"b/{os.path.basename(path)}",
                lineterm="",
            ))

            old_line_count = len(old_string.splitlines()) or 1
            new_line_count = len(new_string.splitlines())
            delta = new_line_count - old_line_count
            delta_str = f"+{delta}" if delta >= 0 else str(delta)

            warning_prefix = f"Warning: {result.warning}\n\n" if result.warning else ""

            return Response(type=ResponseType.TOOL, 
                success=True,
                message=f"{warning_prefix}Edited {path} ({delta_str} lines)",
                files=[path],
                data={
                    "old_lines": old_line_count,
                    "new_lines": new_line_count,
                    "delta": delta,
                    "patch": patch,
                },
            )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error editing file: {e}")
