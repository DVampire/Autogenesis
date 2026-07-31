"""Bash tool for executing shell commands."""
import asyncio
import os
import signal
import sys
from typing import Any, Dict

from pydantic import Field

from autogenesis.permission import Operation, PermissionRequest, permission_manager
from autogenesis.registry import TOOL
from autogenesis.config import config
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType

_DESCRIPTION = "Execute bash commands in the shell."

_INSTRUCTION = """
## Function
Execute bash commands in the shell.

## Guidance
- Use this tool to run system commands, scripts, or any bash operations.
- Be careful with commands that modify the system or require elevated privileges.
- For file operations, ALWAYS use ABSOLUTE paths to avoid path-related issues.
- Input should be a VALID bash command string.
- The command's exit code is reported in the output. A non-zero exit code is an
  observation, not a tool error (e.g. `grep` returns 1 when it finds no matches);
  read STDOUT/STDERR and the exit code to decide whether the command did what you
  intended.

## Parameters
- command (str): The command to execute. If file path is necessary, it should be an absolute path.

## Example
{"name": "bash_tool", "args": {"command": "ls -l /path/to/file.txt"}}
"""


@TOOL.register_module(force=True)
class BashTool(Tool):
    """A tool for executing bash commands asynchronously."""

    name: str = "bash_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    progress_policy: str = "workspace"
    timeout: int = Field(default=600, description="Timeout in seconds for command execution")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, command: str, **kwargs) -> Response:
        """Execute a bash command asynchronously.

        Args:
            command:   The shell command to run.
            workspace_root:  Working directory — used for workspace-boundary checks.
        """
        if not command.strip():
            return Response(type=ResponseType.TOOL, success=False, message="Error: Empty command provided")

        ctx = kwargs.get("ctx")
        # A peer sandbox bound on the context (ctx.extra["sandbox"]) means "route this
        # command into that container" — e.g. a programbench task cleanroom. When absent
        # (the main path), the command runs locally, which under Model X already IS the
        # project container. See BaseContext note.
        sandbox = (getattr(ctx, "extra", None) or {}).get("sandbox")

        # Permission check
        req = PermissionRequest(op=Operation.BASH, target=command)
        result = permission_manager.check(
            self.name, req, workspace=(config.workspace_root or "")
        )
        if not result.allowed:
            return Response(type=ResponseType.TOOL, success=False, message=f"Permission denied: {result.reason}")

        warning_prefix = f"Warning: {result.warning}\n\n" if result.warning else ""

        try:
            if sandbox is not None:
                execution = await asyncio.wait_for(
                    sandbox.run_command(command), timeout=self.timeout
                )
                return Response(
                    type=ResponseType.TOOL,
                    success=execution.success,
                    message=warning_prefix + execution.as_message(),
                    data={"exit_code": execution.exit_code, "command": command, "sandboxed": True},
                )

            # No peer bound: run in the current runtime environment. Under Model X the
            # whole agent runs inside the project container, so "local" execution already
            # IS sandboxed. Keep python3 and pip on the interpreter that launched us.
            runtime_bin = os.path.dirname(sys.executable)
            command_env = {
                **os.environ,
                "PATH": runtime_bin + os.pathsep + os.environ.get("PATH", ""),
            }
            # Every session command runs from its isolated workspace.  Besides
            # keeping relative outputs contained, this makes ordinary scripts
            # (``open('results/x.json', 'w')``) behave consistently with the
            # workspace path shown to the agent.
            workspace_root = config.workspace_root
            cwd = os.path.abspath(workspace_root) if workspace_root else None
            if cwd and not os.path.isdir(cwd):
                return Response(
                    type=ResponseType.TOOL,
                    success=False,
                    message=f"Workspace directory does not exist: {cwd}",
                )
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                env=command_env,
                cwd=cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=f"Error: Command timed out after {self.timeout} seconds",
                )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

            parts = []
            if stdout_str:
                parts.append(f"STDOUT:\n{stdout_str}")
            if stderr_str:
                parts.append(f"STDERR:\n{stderr_str}")

            exit_code = process.returncode
            if exit_code != 0:
                parts.append(f"Exit code: {exit_code}")

            message = warning_prefix + ("\n\n".join(parts) if parts else f"Command completed with exit code: {exit_code}")

            # The bash *tool call* succeeds whenever the command actually ran to
            # completion — the shell exit code is an observation for the model to read
            # (it is included in the message and in `data["exit_code"]`), not a tool
            # malfunction. Treating every non-zero exit as a hard failure mislabels
            # ordinary diagnostics — `grep -c` returns 1 on zero matches, `ls missing`
            # returns 2 — as "❌ Action failed", which floods the logs and can mislead
            # the model into thinking its own deliverables broke. Genuine command
            # failures stay fully visible via STDERR and the exit code; only the tool
            # itself failing (timeout, spawn error, empty command) is success=False.
            return Response(type=ResponseType.TOOL,
                success=True,
                message=message,
                data={"exit_code": exit_code, "command": command},
            )

        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error executing command: {e}")
