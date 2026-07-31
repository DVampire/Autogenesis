"""A run is its own unit of work — its state must not be the session's.

``ctx.id`` scopes everything an agent accumulates: memory, token/step/time
budgets, its todo list. It deliberately scopes nothing on disk (that is
``config.workspace_root``/``log_root``, owned by the bound session), which is
what makes it safe to give a run its own.

Before this, a canvas flow ran under the session's context and so read the
conversation's memory into its prompt and spent its token budget.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from autogenesis.constraint.default.token_constraint import TokenConstraint
from autogenesis.session.types import SessionContext
from autogenesis.workflow.runtime import WorkflowRuntime


def test_a_top_level_run_gets_its_own_scope() -> None:
    session = SessionContext(id="session-1", name="chat")
    scoped = WorkflowRuntime._run_context(session, "run-1", depth=0)

    assert scoped.id == "run-1", "a run must not accumulate state under the session"
    assert session.id == "session-1", "the caller's context must not be mutated"
    # Everything else rides along: the sandbox handle lives in extra, and steps
    # would lose their peer container without it.
    assert scoped.extra == session.extra
    assert scoped.name == session.name


def test_a_nested_run_stays_in_its_parents_scope() -> None:
    """A sub-workflow is part of the same unit of work, not a new one."""
    parent = SessionContext(id="run-1", name="flow")
    assert WorkflowRuntime._run_context(parent, "run-2", depth=1).id == "run-1"


def test_rescoping_is_idempotent() -> None:
    """start() derives, then run() derives again with the same id."""
    ctx = SessionContext(id="session-1")
    once = WorkflowRuntime._run_context(ctx, "run-1", depth=0)
    assert WorkflowRuntime._run_context(once, "run-1", depth=0) is once


def test_a_duck_typed_context_is_left_alone() -> None:
    """Callers pass anything carrying what the steps need; only re-scope a real one."""
    ctx = SimpleNamespace(workspace_root="/tmp/x")
    assert WorkflowRuntime._run_context(ctx, "run-1", depth=0) is ctx


def test_memory_does_not_cross_between_a_conversation_and_a_run() -> None:
    """The prompt-injected memory of one must not contain the other's steps."""
    from autogenesis.memory.default.tiered import TieredMemory
    from autogenesis.trace.types import TraceEvent, TraceEventType

    async def run() -> None:
        memory = TieredMemory()
        session, run_scope = "session-1", "run-1"

        async def note(scope: str, agent: str) -> None:
            await memory.emit(TraceEvent(
                event_type=TraceEventType.AGENT_START, agent_name=agent,
                session_id=scope, input={"task": f"work for {agent}"},
            ), session_id=scope)

        await note(session, "meta_agent")     # the conversation
        await note(run_scope, "general_agent")  # a flow step

        conversation = await memory.get(session_id=session) or ""
        flow = await memory.get(session_id=run_scope) or ""
        assert "meta_agent" in conversation and "general_agent" not in conversation
        assert "general_agent" in flow and "meta_agent" not in flow

    asyncio.run(run())


@pytest.mark.asyncio
async def test_a_run_does_not_spend_the_conversations_budget() -> None:
    constraint = TokenConstraint(max_token=100)

    async def spend(scope: str, tokens: int):
        return await constraint({"token": tokens}, ctx=SimpleNamespace(id=scope))

    await spend("session-1", 90)
    # The same 90 tokens under a run's own scope must not push it over.
    response = await spend("run-1", 90)
    assert response.success, "a run inherited the conversation's spend"

    # …while the conversation itself still hits its own cap.
    response = await spend("session-1", 20)
    assert not response.success


@pytest.mark.asyncio
async def test_a_constraint_frees_the_key_it_counts_under() -> None:
    """The constraint side of the contract the caller was breaking.

    ``_cleanup`` releases whatever ``__call__`` counted under; the agent passed
    it a per-invocation uuid the constraint never sees, so nothing was ever
    released and a session's budget only went up. This pins the two halves to
    the same key — the caller now passes ``ctx.id``.
    """
    constraint = TokenConstraint(max_token=100)
    ctx = SimpleNamespace(id="scope-1")

    await constraint({"token": 90}, ctx=ctx)
    constraint._cleanup(ctx.id)
    response = await constraint({"token": 90}, ctx=ctx)
    assert response.success, "the released budget was not actually released"


def test_the_interpreter_is_keyed_by_project_not_by_state_scope() -> None:
    """Resources are shared; state is not. They cannot use the same key.

    ``ctx.id`` is the state scope — one per conversation, one per workflow run.
    Keying the interpreter off it would hand every new line of dialogue a blank
    one, losing exactly the persistence the tool exists to provide.
    """
    from autogenesis.tool.default.code_interpreter import CodeInterpreterTool
    import autogenesis.tool.default.code_interpreter as module
    from autogenesis.kernel.types import KernelResult

    tool = CodeInterpreterTool()
    captured: list[str] = []

    workspaces: list[str] = []

    class _Recorder:
        async def execute(self, code, *, key="default", **kwargs):
            captured.append(key)
            workspaces.append(kwargs.get("workspace"))
            return KernelResult()

    original, module.kernel_manager = module.kernel_manager, _Recorder()
    try:
        for scope in ("conversation-1", "conversation-2", "workflow-run-3"):
            ctx = SimpleNamespace(id=scope, extra={"project_id": "project-1"},
                                  workspace_root="/projects/one/workspace")
            asyncio.run(tool(code="1+1", ctx=ctx))
    finally:
        module.kernel_manager = original

    assert captured == ["project-1"] * 3, "one interpreter per project, whatever the state scope"
    # And it starts where bash starts, so a relative path means one thing.
    assert workspaces == ["/projects/one/workspace"] * 3


def test_a_figure_survives_as_an_image() -> None:
    """The whole point of carrying MIME bundles: a plot must not become a string.

    The previous pipeline kept only ``text/plain``, so every figure arrived as
    ``<Figure size 640x480 with 1 Axes>``.
    """
    from autogenesis.kernel.types import KernelOutput, KernelResult

    figure = KernelOutput(type="display", data={
        "image/png": "iVBORw0KGgo=", "text/plain": "<Figure size 640x480 with 1 Axes>"})
    result = KernelResult(outputs=[figure])

    assert result.rich() == [figure]
    assert "image/png" in result.as_message()
    # Named, not inlined — base64 in a transcript helps nobody.
    assert "iVBORw0KGgo=" not in result.as_message()
