import asyncio
from pathlib import Path
from types import SimpleNamespace

from autogenesis.permission import PermissionMode
from autogenesis.permission.types import check_file_write, validate_command
from autogenesis.tool.default.bash import BashTool
from autogenesis.config import config


def test_workspace_path_uses_component_boundary(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    assert check_file_write(str(workspace / "ok.txt"), "x", PermissionMode.WORKSPACE_WRITE, str(workspace)).allowed
    sibling = tmp_path / "workspace-escape" / "bad.txt"
    result = check_file_write(str(sibling), "x", PermissionMode.WORKSPACE_WRITE, str(workspace))
    assert not result.allowed


def test_read_only_does_not_trust_general_purpose_executables() -> None:
    from autogenesis.permission.types import CommandIntent, _classify_intent

    for command in ("python -c pass", "node script.js", "curl https://example.com", "tee output"):
        assert _classify_intent(command) is CommandIntent.UNKNOWN
        assert not validate_command(command, PermissionMode.READ_ONLY).allowed


def test_read_only_blocks_chained_redirect_and_git_write() -> None:
    assert not validate_command("ls > output", PermissionMode.READ_ONLY).allowed
    assert not validate_command("git reset --hard", PermissionMode.READ_ONLY).allowed
    assert not validate_command("ls && rm -rf elsewhere", PermissionMode.READ_ONLY).allowed


def test_danger_full_access_bash_runs_locally(tmp_path: Path) -> None:
    # Under Model X the whole agent runs inside the project container, so bash runs
    # the command in the current process environment (which is the container). There
    # is no reach-into-a-separate-sandbox path anymore.
    config.workspace_root = str(tmp_path)
    tool = BashTool(permission_mode="danger_full_access")
    ctx = SimpleNamespace(extra={})
    response = asyncio.run(tool(command="echo hello-sandbox", ctx=ctx))
    assert response.success
    assert "hello-sandbox" in response.message
    assert "sandboxed" not in (response.data or {})

