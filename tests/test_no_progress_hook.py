import pytest
from types import SimpleNamespace

from autogenesis.agent.types import Agent, AgentContext
from autogenesis.hook import hook_manager
from autogenesis.hook.default.no_progress import NoProgressHook, progress_policy
from autogenesis.hook.types import HookContext, HookDecision, HookEvent


class _GuardAgent(Agent):
    name: str = "guard_agent"
    description: str = "test"
    metadata: dict = {}

    async def _post_step(self, *args, **kwargs):
        self.posted = getattr(self, "posted", 0) + 1

    async def _advance(self, run):
        self.advanced = getattr(self, "advanced", 0) + 1

    async def _conclude(self, run):
        self.concluded = getattr(self, "concluded", 0) + 1


def _context(actions, evidence=None, fingerprint="same"):
    return HookContext(
        id="run-1",
        name="no_progress_hook",
        workspace_root="/tmp/workspace",
        input={
            "event": HookEvent.PRE_ACTION,
            "actions": actions,
            "evidence": evidence or {},
            "workspace_fingerprint": fingerprint,
        },
    )


@pytest.mark.asyncio
async def test_blocks_unchanged_successful_workspace_action():
    hook = NoProgressHook()
    action = {"name": "read_file_tool", "kind": "tool", "signature": "read", "policy": "workspace"}
    result = await hook.handle(_context(
        [action],
        {"read": {"success": True, "workspace_fingerprint": "same"}},
    ))
    assert result.decision == HookDecision.BLOCK
    assert "read_file_tool" in result.reason


@pytest.mark.asyncio
async def test_allows_repeat_after_workspace_changes():
    hook = NoProgressHook()
    action = {"name": "bash_tool", "kind": "tool", "signature": "test", "policy": "workspace"}
    result = await hook.handle(_context(
        [action],
        {"test": {"success": True, "workspace_fingerprint": "before"}},
        fingerprint="after",
    ))
    assert result.decision == HookDecision.ALLOW


@pytest.mark.asyncio
async def test_external_polling_and_mutating_actions_are_not_blocked():
    hook = NoProgressHook()
    actions = [
        {"name": "web_searcher_tool", "kind": "tool", "signature": "search"},
        {"name": "wait_tool", "kind": "tool", "signature": "wait"},
        {"name": "write_file_tool", "kind": "tool", "signature": "write"},
    ]
    evidence = {
        action["signature"]: {"success": True, "workspace_fingerprint": "same"}
        for action in actions
    }
    result = await hook.handle(_context(actions, evidence))
    assert result.decision == HookDecision.ALLOW
    assert [progress_policy(action) for action in actions] == ["external", "polling", "always"]


@pytest.mark.asyncio
async def test_base_agent_skips_repeat_and_feeds_correction(tmp_path):
    await hook_manager.initialize(hook_names=["no_progress_hook"])
    agent = _GuardAgent(base_dir=str(tmp_path), use_memory=False)
    ctx = AgentContext(id="ctx", workspace_root=str(tmp_path))
    call = SimpleNamespace(name="read_file_tool", input={"path": str(tmp_path / "a.py")})
    signature = agent._action_signature("tool", call.name, call.input)
    run = SimpleNamespace(
        task_id="task", ctx=ctx, action_evidence={
            signature: {
                "success": True,
                "workspace_fingerprint": agent._workspace_fingerprint(ctx),
            }
        },
        no_progress_rounds=0, step=1, messages=[], action_errors=[],
        done=False, result=None, reasoning=None,
    )
    decision = {
        "tool_calls": [call],
        "routing": {call.name: ("tool", call.name)},
        "reasoning": "repeat",
        "step_tokens": 1,
    }

    assert await agent._prepare_round(run, decision) is None
    assert run.step == 2
    assert run.no_progress_rounds == 1
    assert "No-progress guard" in run.action_errors[0]
    assert agent.posted == 1
    assert agent.advanced == 1


@pytest.mark.asyncio
async def test_base_agent_stops_third_no_progress_proposal(tmp_path):
    await hook_manager.initialize(hook_names=["no_progress_hook"])
    agent = _GuardAgent(base_dir=str(tmp_path), use_memory=False)
    ctx = AgentContext(id="ctx", workspace_root=str(tmp_path))
    call = SimpleNamespace(name="read_file_tool", input={"path": str(tmp_path / "a.py")})
    signature = agent._action_signature("tool", call.name, call.input)
    run = SimpleNamespace(
        task_id="task", ctx=ctx, action_evidence={
            signature: {
                "success": True,
                "workspace_fingerprint": agent._workspace_fingerprint(ctx),
            }
        },
        no_progress_rounds=2, step=3, messages=[], action_errors=[],
        done=False, result=None, reasoning=None,
    )
    decision = {
        "tool_calls": [call],
        "routing": {call.name: ("tool", call.name)},
        "reasoning": "repeat",
        "step_tokens": 1,
    }

    assert await agent._prepare_round(run, decision) is None
    assert run.done is False
    assert "three no-progress" in run.result
    assert agent.concluded == 1
