import argparse
import os
import sys
from pathlib import Path

import pytest

root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from autogenesis.config import config


def test_programbench_agent_config_loads_expected_base_roster():
    config.initialize(
        config_path=os.path.join(root, "configs", "programbench_agent.py"),
        args=argparse.Namespace(),
        verbose=False,
    )
    assert "meta_agent" in config.agent_names
    assert "code_agent" in config.agent_names
    assert "general_agent" in config.agent_names
    assert "reviewer_agent" in config.agent_names
    # monitor_agent is deliberately excluded — it spawns its own bash subprocess
    # directly, bypassing the Docker sandbox bash_tool routes through.
    assert "monitor_agent" not in config.agent_names
    # Base roster excludes the self-evolution add-ons — the running script adds
    # them at runtime via extend_roster_for_evolve() when --evolve is set.
    assert "tool_optimize_agent" not in config.agent_names
    assert "connector_evaluate_agent" not in config.agent_names
    assert "bash_tool" in config.tool_names
    assert "evolution_tool" not in config.tool_names
    # None of these check get_current_sandbox() — they'd silently operate on the
    # host workspace instead of the container once a sandbox is bound.
    assert "read_file_tool" not in config.tool_names
    assert "write_file_tool" not in config.tool_names
    assert "edit_file_tool" not in config.tool_names
    assert "list_dir_tool" not in config.tool_names
    assert "git_tool" not in config.tool_names
    assert "run_skill" in config.skill_names
    assert "self_evolving_skill" not in config.skill_names
    assert config.connector_names == []
    assert config.env_names == []


sys.path.append(str(Path(root) / "examples"))

import run_programbench as rp  # noqa: E402


def test_select_instances_by_task_ids():
    instances = [
        {"instance_id": "a", "repository": "repo-a"},
        {"instance_id": "b", "repository": "repo-b"},
        {"instance_id": "c", "repository": "repo-c"},
    ]
    selected, warnings = rp.select_instances(instances, task_ids=["c", "a"])
    assert [i["instance_id"] for i in selected] == ["c", "a"]
    assert warnings == []


def test_select_instances_by_task_ids_skips_unknown():
    instances = [{"instance_id": "a"}, {"instance_id": "b"}]
    selected, warnings = rp.select_instances(instances, task_ids=["a", "does-not-exist"])
    assert [i["instance_id"] for i in selected] == ["a"]
    assert warnings == ["unknown task id(s) skipped: ['does-not-exist']"]


def test_select_instances_by_range():
    instances = [{"instance_id": str(i)} for i in range(10)]
    selected, warnings = rp.select_instances(instances, start=2, end=5)
    assert [i["instance_id"] for i in selected] == ["2", "3", "4"]
    assert warnings == []


def test_select_instances_task_ids_take_precedence_over_range():
    instances = [{"instance_id": "a"}, {"instance_id": "b"}]
    selected, warnings = rp.select_instances(instances, task_ids=["b"], start=0, end=1)
    assert [i["instance_id"] for i in selected] == ["b"]
    assert warnings == ["--start/--end ignored because --task-ids was given"]


def test_select_instances_requires_a_selector():
    with pytest.raises(ValueError):
        rp.select_instances([{"instance_id": "a"}])


def test_build_task_content_includes_system_prompt_and_fields():
    instance = {
        "repository": "abishekvashok/cmatrix",
        "language": "c",
        "image_name": "programbench/abishekvashok_1776_cmatrix.5c082c6",
        "commit": "5c082c6",
    }
    content = rp.build_task_content(instance)
    assert rp.SYSTEM_PROMPT.strip() in content
    assert "abishekvashok/cmatrix" in content
    assert "language: c" in content
    assert "./executable" in content
    assert "./compile.sh" in content


def test_extend_roster_for_evolve_off_is_unchanged():
    agents, tools, skills = rp.extend_roster_for_evolve(
        ["meta_agent"], ["bash_tool"], ["run_skill"], evolve=False,
    )
    assert agents == ["meta_agent"]
    assert tools == ["bash_tool"]
    assert skills == ["run_skill"]


def test_extend_roster_for_evolve_on_adds_triads():
    agents, tools, skills = rp.extend_roster_for_evolve(
        ["meta_agent"], ["bash_tool"], ["run_skill"], evolve=True,
    )
    assert "tool_optimize_agent" in agents
    assert "connector_evaluate_agent" in agents
    assert len(agents) == 1 + len(rp.EVOLVE_AGENT_NAMES)
    assert "evolution_tool" in tools
    assert "self_evolving_skill" in skills
    assert "agent_creator_skill" in skills


def test_extend_roster_for_evolve_does_not_mutate_input_lists():
    base_agents = ["meta_agent"]
    rp.extend_roster_for_evolve(base_agents, [], [], evolve=True)
    assert base_agents == ["meta_agent"]


def test_parse_args_requires_a_selector():
    old_argv = sys.argv
    sys.argv = ["run_programbench.py"]
    try:
        with pytest.raises(SystemExit):
            rp.parse_args()
    finally:
        sys.argv = old_argv


def test_parse_args_evolve_defaults_to_true():
    old_argv = sys.argv
    sys.argv = ["run_programbench.py", "--start", "0", "--end", "1"]
    try:
        args = rp.parse_args()
    finally:
        sys.argv = old_argv
    assert args.evolve is True


def test_parse_args_no_evolve_flag():
    old_argv = sys.argv
    sys.argv = ["run_programbench.py", "--start", "0", "--end", "1", "--no-evolve"]
    try:
        args = rp.parse_args()
    finally:
        sys.argv = old_argv
    assert args.evolve is False


def test_parse_args_task_ids():
    old_argv = sys.argv
    sys.argv = ["run_programbench.py", "--task-ids", "a,b, c"]
    try:
        args = rp.parse_args()
    finally:
        sys.argv = old_argv
    assert args.task_ids == "a,b, c"


class _FakeExecResult:
    def __init__(self, success):
        self.success = success

    def as_message(self):
        return "ok" if self.success else "tar: command failed"


class _FakeSandbox:
    """Minimal stand-in for a real OpenSandbox handle — no Docker involved."""

    def __init__(self, tar_bytes=b"fake-tar-bytes", command_success=True):
        self._tar_bytes = tar_bytes
        self._command_success = command_success
        self.commands_run = []

    async def run_command(self, command):
        self.commands_run.append(command)
        return _FakeExecResult(self._command_success)

    async def read_bytes(self, path):
        assert path == "/tmp/submission.tar.gz"
        return self._tar_bytes


@pytest.mark.asyncio
async def test_extract_submission_writes_tar_to_dest_dir(tmp_path):
    # extract_submission pulls the tarball out AND unpacks it host-side for
    # inspection, so the fake sandbox must return a real gzip tar (not a raw
    # placeholder) or the unpack step raises tarfile.ReadError.
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        member = tarfile.TarInfo(name="hello.txt")
        payload = b"hello-tar"
        member.size = len(payload)
        tf.addfile(member, io.BytesIO(payload))
    tar_bytes = buf.getvalue()

    sandbox = _FakeSandbox(tar_bytes=tar_bytes)
    dest_dir = str(tmp_path / "workspace")

    result_path = await rp.extract_submission(sandbox, dest_dir)

    assert result_path == str(Path(dest_dir) / "submission.tar.gz")
    with open(result_path, "rb") as f:
        assert f.read() == tar_bytes
    assert sandbox.commands_run == ["tar -czf /tmp/submission.tar.gz -C /workspace . 2>&1"]
    # The tarball is also unpacked into dest_dir/submission/ for direct inspection.
    unpacked = Path(dest_dir) / "submission" / "hello.txt"
    assert unpacked.read_bytes() == b"hello-tar"


@pytest.mark.asyncio
async def test_extract_submission_raises_on_tar_failure():
    sandbox = _FakeSandbox(command_success=False)

    with pytest.raises(RuntimeError):
        await rp.extract_submission(sandbox, "/tmp/wherever")
