"""GitTool — git operations scoped to a workspace_root."""

import asyncio
import os
from typing import Dict, Any, Optional
from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL
from autogenesis.config import config

_DESCRIPTION = "Run git operations inside the project workspace_root."

_INSTRUCTION = """
## Function
Run git operations inside the project workspace_root.

## Guidance
Available actions:
- status: Show working tree status.
- diff: Show unstaged changes. Optionally pass a file path.
- diff_staged: Show staged (cached) changes.
- log: Show recent commit history. Optionally pass count (default 10).
- add: Stage files. Pass path="." to stage all, or a specific file path.
- commit: Create a commit. Requires message parameter.
- checkout: Checkout a branch or restore a file. Pass target (branch name or file path).
- branch: List branches.

## Parameters
- action (str): One of: status, diff, diff_staged, log, add, commit, checkout, branch.
- path (str, optional): File or directory path for diff/add/checkout actions.
- message (str, optional): Commit message for commit action.
- count (int, optional): Number of log entries to show (default 10).

## Example
{"name": "git_tool", "args": {"action": "status"}}
{"name": "git_tool", "args": {"action": "diff", "path": "src/foo.py"}}
{"name": "git_tool", "args": {"action": "add", "path": "."}}
{"name": "git_tool", "args": {"action": "commit", "message": "fix: handle edge case in parser"}}
{"name": "git_tool", "args": {"action": "log", "count": 5}}
"""


@TOOL.register_module(force=True)
class GitTool(Tool):
    """Git operations scoped to the session workspace_root."""

    name: str = "git_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={})
    enable_evolving: bool = Field(default=False)
    timeout: int = Field(default=60)

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def _run(self, args: list[str], cwd: str, sandbox=None) -> tuple[int, str, str]:
        """Run a git command, return (returncode, stdout, stderr).

        When a peer ``sandbox`` is bound on the context, the command runs inside it
        (git -C <cwd> ...); otherwise it runs locally (Model X: the project container).
        """
        if sandbox is not None:
            import shlex as _shlex
            cmd = "git -C " + _shlex.quote(cwd) + " " + " ".join(_shlex.quote(a) for a in args)
            res = await sandbox.run_command(cmd)
            return (res.exit_code if res.exit_code is not None else (0 if res.success else 1),
                    res.stdout or "", res.stderr or res.error or "")
        process = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            await process.wait()
            return -1, "", f"git command timed out after {self.timeout}s"

        return (
            process.returncode,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )

    def _get_workspace_root(self, ctx) -> Optional[str]:
        """Return the workspace root from the call context, or None if unavailable.

        Used to scope git operations to the session's workspace directory.
        """
        # Working dir comes from the global config (set per-run by bind_session_roots),
        # not from ctx — see BaseContext note on why workspace_root is config-owned.
        return config.workspace_root or None

    async def __call__(
        self,
        action: str,
        path: Optional[str] = None,
        message: Optional[str] = None,
        count: int = 10,
        **kwargs,
    ) -> Response:
        """Execute a git operation.

        Args:
            action: Git action to perform.
            path: Optional file/directory path.
            message: Commit message (for commit action).
            count: Number of log entries (for log action).
        """
        ctx = kwargs.get("ctx")
        sandbox = (getattr(ctx, "extra", None) or {}).get("sandbox")
        if sandbox is not None:
            # git runs inside the peer container: use the peer's own workspace dir
            # (e.g. /workspace), not the host session path — that path does not exist
            # in the peer's filesystem. No local isdir check for the same reason.
            workspace_root = sandbox.container_workspace or self._get_workspace_root(ctx)
            if not workspace_root:
                return Response(type=ResponseType.TOOL, success=False, message="Error: No workspace_root set in context.")
        else:
            workspace_root = self._get_workspace_root(ctx)
            if not workspace_root:
                return Response(type=ResponseType.TOOL, success=False, message="Error: No workspace_root set in context.")
            if not os.path.isdir(workspace_root):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: workspace_root not found: {workspace_root}")

        try:
            if action == "status":
                rc, out, err = await self._run(["status"], workspace_root, sandbox)
                return self._respond(rc, out, err, "status")

            elif action == "diff":
                git_args = ["diff"]
                if path:
                    git_args.append(path)
                rc, out, err = await self._run(git_args, workspace_root, sandbox)
                return self._respond(rc, out or "(no unstaged changes)", err, "diff")

            elif action == "diff_staged":
                git_args = ["diff", "--cached"]
                if path:
                    git_args.append(path)
                rc, out, err = await self._run(git_args, workspace_root, sandbox)
                return self._respond(rc, out or "(no staged changes)", err, "diff --cached")

            elif action == "log":
                rc, out, err = await self._run(
                    ["log", f"--max-count={count}", "--oneline", "--decorate"], workspace_root, sandbox
                )
                return self._respond(rc, out or "(no commits)", err, "log")

            elif action == "add":
                target = path or "."
                rc, out, err = await self._run(["add", target], workspace_root, sandbox)
                msg = f"Staged: {target}" if rc == 0 else err
                return self._respond(rc, msg, err, "add")

            elif action == "commit":
                if not message:
                    return Response(type=ResponseType.TOOL, success=False, message="Error: commit requires a message parameter.")
                rc, out, err = await self._run(["commit", "-m", message], workspace_root, sandbox)
                return self._respond(rc, out or err, err, "commit")

            elif action == "checkout":
                if not path:
                    return Response(type=ResponseType.TOOL, success=False, message="Error: checkout requires a target (branch or file path).")
                rc, out, err = await self._run(["checkout", path], workspace_root, sandbox)
                return self._respond(rc, out or err or f"Checked out: {path}", err, "checkout")

            elif action == "branch":
                rc, out, err = await self._run(["branch", "-a"], workspace_root, sandbox)
                return self._respond(rc, out or "(no branches)", err, "branch")

            else:
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=f"Unknown action: {action}. Available: status, diff, diff_staged, log, add, commit, checkout, branch",
                )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error running git {action}: {e}")

    @staticmethod
    def _respond(rc: int, stdout: str, stderr: str, action: str) -> Response:
        """Wrap a git subprocess result into a tool Response.

        A zero return code yields a success Response carrying stdout; otherwise a
        failure Response is built from stderr (falling back to stdout or a
        generic exit-code message).

        Args:
            rc: Process exit code (0 means success).
            stdout: Captured standard output.
            stderr: Captured standard error.
            action: Git action name, echoed back in the success payload.
        """
        success = rc == 0
        if success:
            return Response(type=ResponseType.TOOL, success=True, message=stdout, data={"action": action})
        else:
            msg = stderr or stdout or f"git {action} failed (exit {rc})"
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {msg}")
