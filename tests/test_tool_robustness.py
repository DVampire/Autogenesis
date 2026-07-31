"""Regression tests for tool-layer robustness fixes.

Three papercuts observed in a real MetaAgent run, each fixed and pinned here:

1. A model tool call that omits a required parameter (e.g. ``done_tool`` without
   ``result``) used to raise a raw ``TypeError`` out of the central dispatch and
   surface as an opaque "Action failed" — now it returns a clean, recoverable
   Response naming the missing parameter.
2. ``bash_tool`` used to mark every non-zero exit code as ``success=False``, so
   ordinary diagnostics (``grep -c`` with no match → exit 1, ``ls missing`` →
   exit 2) were mislabeled as failed actions. A command that runs to completion is
   now a successful observation with the exit code carried in ``data``/message.
"""
import asyncio
from types import SimpleNamespace

import pytest

from autogenesis.config import config
from autogenesis.tool.context import ToolContextManager
from autogenesis.tool.default.bash import BashTool
from autogenesis.tool.default.done import DoneTool


# --------------------------------------------------------------------------- #
# Fix #2 — missing/invalid arguments become a recoverable tool error
# --------------------------------------------------------------------------- #
def _manager_for(tmp_path, instance):
    manager = ToolContextManager(base_dir=str(tmp_path))

    async def _fake_get_info(name):
        return SimpleNamespace(version="1.0.0", instance=instance)

    manager.get_info = _fake_get_info
    return manager


@pytest.mark.asyncio
async def test_missing_required_arg_returns_clean_error_not_typeerror(tmp_path):
    manager = _manager_for(tmp_path, DoneTool())
    # done_tool requires both `reasoning` and `result`; omit `result`.
    resp = await manager(name="done_tool", input={"reasoning": "all conditions met"})
    assert resp.success is False
    # The message names the offending tool and the parameter the model forgot,
    # rather than leaking "__call__() missing 1 required positional argument".
    assert "done_tool" in resp.message
    assert "result" in resp.message
    assert "positional argument" not in resp.message


@pytest.mark.asyncio
async def test_valid_call_still_dispatches(tmp_path):
    manager = _manager_for(tmp_path, DoneTool())
    resp = await manager(name="done_tool", input={"reasoning": "r", "result": "ok"})
    assert resp.success is True
    assert resp.message == "ok"


@pytest.mark.asyncio
async def test_in_body_errors_are_not_masked_by_bind_check(tmp_path):
    class _Boom(DoneTool):
        async def __call__(self, reasoning: str, result: str, **kwargs):
            raise ValueError("boom inside body")

    manager = _manager_for(tmp_path, _Boom())
    # The bind check must only catch argument-binding errors; a genuine error
    # raised inside the tool body must still propagate untouched.
    with pytest.raises(ValueError, match="boom inside body"):
        await manager(name="done_tool", input={"reasoning": "r", "result": "ok"})


# --------------------------------------------------------------------------- #
# Fix #3 — a bash command that runs is a success, exit code is an observation
# --------------------------------------------------------------------------- #
def test_bash_nonzero_exit_is_successful_observation(tmp_path):
    config.workspace_root = str(tmp_path)
    tool = BashTool(permission_mode="danger_full_access")
    ctx = SimpleNamespace(extra={})
    # `grep -c` prints "0" and exits 1 when there are no matches — the canonical
    # false-failure case.
    resp = asyncio.run(tool(command="echo needle | grep -c missing", ctx=ctx))
    assert resp.success is True
    assert resp.data["exit_code"] == 1
    assert "Exit code: 1" in resp.message


def test_bash_true_failure_still_visible(tmp_path):
    config.workspace_root = str(tmp_path)
    tool = BashTool(permission_mode="danger_full_access")
    ctx = SimpleNamespace(extra={})
    resp = asyncio.run(tool(command="ls /no/such/path/here", ctx=ctx))
    # The tool call succeeds (it ran), but the failure is fully legible: the
    # exit code and stderr are in the response for the model to read.
    assert resp.success is True
    assert resp.data["exit_code"] != 0
    assert "Exit code:" in resp.message
    assert "STDERR" in resp.message


def test_bash_empty_command_is_a_tool_error(tmp_path):
    config.workspace_root = str(tmp_path)
    tool = BashTool(permission_mode="danger_full_access")
    ctx = SimpleNamespace(extra={})
    resp = asyncio.run(tool(command="   ", ctx=ctx))
    assert resp.success is False
