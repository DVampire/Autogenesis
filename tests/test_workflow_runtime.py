import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autogenesis.config import config
from autogenesis.paths import P, path_manager
from autogenesis.workflow import (
    ExecutionState, InvocationState, WorkflowCompileError, WorkflowEvaluation,
    WorkflowContextManager, WorkflowRuntime, WorkflowState, WorkflowStatus,
    WorkflowRun, workflow_compiler, workflow_manager, workflow_runtime,
)


class FakeRuntime(WorkflowRuntime):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler
        self.calls = []
        self.kinds = []

    async def _validate_capabilities(self, definition):
        return None

    async def _invoke(self, kind, target, task, args, ctx, depth, budget=None):
        self.kinds.append(kind)
        self.calls.append((target, task, args))
        value = self.handler(target, task, args)
        return await value if asyncio.iscoroutine(value) else value


def retain_successful_run(definition, run_id, token_cost=0):
    run = WorkflowRun(
        id=run_id, workflow_name=definition.name, workflow_version=definition.version,
        program_hash=definition.program_hash, state=WorkflowState.SUCCEEDED,
        token_cost=token_cost,
        started_at="2026-01-01T00:00:00+00:00", finished_at="2026-01-01T00:00:01+00:00",
    )
    workflow_runtime._runs[run_id] = run
    return run


HTML = """
<workflow name="dynamic_audit" version="1.2.0" description="Dynamic file audit"
          max-agents="20" max-concurrency="4" enable-evolving="true">
  <inputs><input name="files" type="array" required="true" /></inputs>
  <applicability><tag>audit</tag><tag>parallel</tag>Use for many files.</applicability>
  <flow>
    <map id="audits" items="${inputs.files}" as="file" concurrency="3">
      <agent id="audit" name="audit_agent" task="Audit ${file}">
        <arg name="path" value="${file}" />
      </agent>
    </map>
    <verify id="verified" items="${audits}" as="finding" agent="verify_agent"
            task="Verify ${finding}" concurrency="2" />
    <reduce id="summary" items="${verified}" agent="summary_agent" task="Summarize" />
  </flow>
  <outputs><output name="report" value="${summary.data}" /></outputs>
</workflow>
"""


def complete_html(workflow_source):
    return f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{workflow_source}</body></html>"


def test_compiler_builds_dynamic_program_and_metadata():
    definition = workflow_compiler.compile(HTML)
    assert definition.name == "dynamic_audit"
    assert definition.tags == ["audit", "parallel"]
    assert definition.enable_evolving is True
    assert [step.type.value for step in definition.program] == ["map", "verify", "reduce"]
    assert definition.program[0].children[0].task == "Audit ${file}"


@pytest.mark.asyncio
async def test_context_owns_discovery_projection_cache_and_evidence(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    (builtins / "dynamic_audit.html").write_text(complete_html(HTML), encoding="utf-8")
    evidence = tmp_path / "evaluations.json"
    context = WorkflowContextManager(builtin_dir=builtins, evaluation_path=evidence)

    await context.initialize()
    assert context.list() == ["dynamic_audit"]
    assert "dynamic_audit" in context.get_instruction()
    assert context.get_instruction(allowlist=[]) == ""
    schemas = await context.function_callings()
    assert schemas[0][0]["function"]["name"] == "workflow__dynamic_audit"
    assert schemas[0][1] == ("workflow", "dynamic_audit")

    context.register(HTML.replace('name="dynamic_audit"', 'name="second_flow"'), override=True)
    assert "second_flow" in context.get_instruction()  # registration invalidated the cache
    v2 = context.register(
        HTML.replace('version="1.2.0"', 'version="1.3.0"'), override=True,
    )
    assert v2.version == "1.3.0"
    assert context.restore("dynamic_audit", "1.2.0").version == "1.2.0"
    retain_successful_run(context.get("dynamic_audit"), "context-test")
    context.record_evaluation(WorkflowEvaluation(
        workflow_name="dynamic_audit", workflow_version="1.2.0",
        run_id="context-test", success=True, quality_score=0.9,
    ))
    assert evidence.exists()

    restored = WorkflowContextManager(builtin_dir=builtins, evaluation_path=evidence)
    await restored.initialize()
    assert restored.evaluation_summary("dynamic_audit")["runs"] == 1
    await restored.cleanup()
    assert restored.list() == []
    workflow_runtime._runs.pop("context-test", None)


def test_compiler_rejects_unsafe_or_unbounded_programs():
    with pytest.raises(WorkflowCompileError, match="renderer script"):
        workflow_compiler.compile('<workflow name="bad"><flow><script>evil()</script></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="bounded"):
        workflow_compiler.compile('<workflow name="bad"><flow><loop id="x"><agent name="a"/></loop></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="max-agents"):
        workflow_compiler.compile('<workflow name="bad" max-agents="1001"><flow><agent name="a"/></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="schema-version"):
        workflow_compiler.compile('<workflow name="future" schema-version="2.0.0"><flow><agent name="a"/></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="version"):
        workflow_compiler.compile('<workflow name="bad" version="latest"><flow><agent name="a"/></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="Event handler"):
        workflow_compiler.compile('<workflow name="bad" onclick="evil()"><flow><agent name="a"/></flow></workflow>')
    with pytest.raises(WorkflowCompileError, match="Remote"):
        workflow_compiler.compile('''
          <html><body><script src="https://evil.example/visual/js/workflow.js"></script>
          <workflow name="bad"><flow><checkpoint /></flow></workflow></body></html>
        ''')
    with pytest.raises(WorkflowCompileError, match="conflicts"):
        workflow_compiler.compile('''
          <workflow name="bad"><inputs><input name="items" type="string" />
          <schema for="items">{"type":"array"}</schema></inputs>
          <flow><checkpoint id="saved" /></flow></workflow>
        ''')
    with pytest.raises(WorkflowCompileError, match="guaranteed top-level"):
        workflow_compiler.compile('''
          <workflow name="bad"><flow><branch id="choice" test="${inputs.flag}">
          <then><agent id="conditional" name="worker" /></then></branch></flow>
          <outputs><output name="result" value="${conditional}" /></outputs></workflow>
        ''')


@pytest.mark.asyncio
async def test_dynamic_map_verify_reduce_and_checkpoint(tmp_path):
    config.workspace_root = str(tmp_path)
    active = peak = 0

    async def handler(target, task, args):
        nonlocal active, peak
        if target == "audit_agent":
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"path": args["path"], "issue": True}
        if target == "verify_agent":
            return {"accepted": True, "finding": args["finding"]}
        return {"data": {"count": len(args["items"])}}

    runtime = FakeRuntime(handler)
    run = await runtime.run(
        workflow_compiler.compile(HTML), input={"files": ["a.py", "b.py", "c.py"]},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert run.state == WorkflowState.SUCCEEDED
    assert run.output == {"report": {"count": 3}}
    assert run.agent_count == 7
    assert peak == 3
    saved = json.loads(Path(run.checkpoint_path).read_text())
    # Bookkeeping lives in the layout, never inside the agent's workspace.
    assert Path(run.checkpoint_path).parent == path_manager.get(P.CHECKPOINTS)
    assert saved["state"] == "succeeded"


@pytest.mark.asyncio
async def test_branch_loop_and_resume_cache(tmp_path):
    calls = 0
    source = """
    <workflow name="repair">
      <flow>
        <loop id="repair_loop" max-rounds="3" until="${check.success}">
          <agent id="check" name="checker" />
          <branch id="fix_if_needed" test="not check.success">
            <then><agent id="fix" name="fixer" /></then>
          </branch>
        </loop>
      </flow>
    </workflow>
    """
    def handler(target, task, args):
        nonlocal calls
        calls += 1
        return {"success": calls >= 3} if target == "checker" else {"fixed": True}
    runtime = FakeRuntime(handler)
    definition = workflow_compiler.compile(source)
    run = await runtime.run(definition, ctx=SimpleNamespace(workspace_root=str(tmp_path)))
    assert run.successful
    assert calls == 3
    resumed = await runtime.resume(definition, run.checkpoint_path, ctx=SimpleNamespace(workspace_root=str(tmp_path)))
    assert resumed.successful
    assert calls == 3  # completed agent invocations came from checkpoint cache
    assert all(item.state == InvocationState.CACHED for item in resumed.invocations.values())
    assert any(item.state == ExecutionState.CACHED for item in resumed.frames.values())


@pytest.mark.asyncio
async def test_while_and_independent_verification_votes(tmp_path):
    checks = 0
    source = """
    <workflow name="votes" max-concurrency="2">
      <inputs><input name="keep_going" type="boolean" required="true" /></inputs>
      <flow>
        <loop id="rounds" max-rounds="2" while="${inputs.keep_going}">
          <agent id="work" name="worker" />
        </loop>
        <verify id="votes" items="${rounds}" as="result" agent="reviewer" min-votes="2" />
      </flow>
    </workflow>
    """
    def handler(target, task, args):
        nonlocal checks
        checks += 1
        return {"target": target, "n": checks}
    runtime = FakeRuntime(handler)
    run = await runtime.run(
        workflow_compiler.compile(source), input={"keep_going": True},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert run.successful
    assert run.agent_count == 6  # two workers + two independent votes for each result
    assert all(len(item["verdicts"]) == 2 for item in run.variables["votes"])


@pytest.mark.asyncio
async def test_manager_projects_every_active_workflow_directly():
    active = workflow_manager.register(HTML, override=True)
    second = workflow_manager.register(HTML.replace('name="dynamic_audit"', 'name="second_audit"'), override=True)
    try:
        assert set(item.name for item in workflow_manager.search("parallel")) == {active.name, second.name}
        schemas = await workflow_manager.function_callings()
        names = {entry[0]["function"]["name"] for entry in schemas}
        assert "workflow__dynamic_audit" in names
        assert "workflow__second_audit" in names
        assert not names & {
            "search_workflows", "run_dynamic_workflow", "register_workflow_candidate",
        }
        assert next(route for schema, route in schemas if schema["function"]["name"] == "workflow__dynamic_audit") == ("workflow", "dynamic_audit")
    finally:
        workflow_manager.unregister(active.name)
        workflow_manager.unregister(second.name)


@pytest.mark.asyncio
async def test_extension_loads_html_workflow(tmp_path):
    from autogenesis.extension.server import ExtensionManagerServer
    path = tmp_path / "audit.html"
    path.write_text(complete_html(HTML), encoding="utf-8")
    manager = ExtensionManagerServer(base_dir=str(tmp_path / "extensions"))
    name = await manager._load_component("workflow", str(path), None, None, None)
    try:
        assert workflow_manager.get(name).source_path == str(path.resolve())
    finally:
        workflow_manager.unregister(name)


@pytest.mark.asyncio
async def test_active_workflow_is_persisted_and_version_archived(tmp_path):
    from autogenesis.extension import extension_manager

    previous = extension_manager.base_dir
    extension_manager.set_base_dir(str(tmp_path / "extensions"))
    source = HTML.replace('name="dynamic_audit"', 'name="saved_workflow"')
    try:
        active = Path(extension_manager.stage_path("workflow", "saved_workflow.html"))
        active.write_text(complete_html(source), encoding="utf-8")
        name = await extension_manager.add_component("workflow", str(active), run_smoke=False)
        definition = workflow_manager.get(name)
        archive = tmp_path / "extensions/.versions/workflow/saved_workflow/1.2.0.html"
        assert definition.status == WorkflowStatus.ACTIVE
        assert active.exists() and archive.exists()
    finally:
        workflow_manager.unregister("saved_workflow")
        extension_manager.set_base_dir(previous)


@pytest.mark.asyncio
async def test_complete_run_state_machine_pause_continue_and_hierarchy(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()
    source = """
    <workflow name="controlled" schema-version="1.0.0">
      <flow>
        <agent id="first" name="worker" />
        <agent id="second" name="worker" />
      </flow>
    </workflow>
    """
    calls = 0
    async def handler(target, task, args):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
        return {"call": calls}

    runtime = FakeRuntime(handler)
    run_id = runtime.start(
        workflow_compiler.compile(source),
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    assert runtime.pause(run_id)
    assert runtime.get_run(run_id).state == WorkflowState.PAUSING
    release.set()
    for _ in range(100):
        if runtime.get_run(run_id).state == WorkflowState.PAUSED:
            break
        await asyncio.sleep(0.01)
    assert runtime.get_run(run_id).state == WorkflowState.PAUSED
    assert runtime.continue_run(run_id)
    for _ in range(100):
        if runtime.get_run(run_id).state == WorkflowState.SUCCEEDED:
            break
        await asyncio.sleep(0.01)
    run = runtime.get_run(run_id)
    assert run.state == WorkflowState.SUCCEEDED
    assert len(run.frames) == 2 and len(run.invocations) == 2
    assert all(item.state == InvocationState.COMPLETED for item in run.invocations.values())
    assert all(item.attempts[0].state == InvocationState.COMPLETED for item in run.invocations.values())


@pytest.mark.asyncio
async def test_json_schema_is_enforced_at_runtime(tmp_path):
    source = """
    <workflow name="schema_guard">
      <inputs>
        <input name="files" type="array" required="true" />
        <schema for="files">{"type":"array","items":{"type":"string"},"minItems":2}</schema>
      </inputs>
      <flow><checkpoint id="saved" /></flow>
    </workflow>
    """
    runtime = FakeRuntime(lambda *_: None)
    definition = workflow_compiler.compile(source)
    too_short = await runtime.run(
        definition, input={"files": ["one"]},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert too_short.state == WorkflowState.REJECTED
    extra = await runtime.run(
        definition, input={"files": ["one", "two"], "unexpected": True},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert extra.state == WorkflowState.REJECTED


@pytest.mark.asyncio
async def test_step_timeout_environment_node_and_retry_attempts(tmp_path):
    async def slow(*_):
        await asyncio.sleep(1)

    runtime = FakeRuntime(slow)
    definition = workflow_compiler.compile("""
      <workflow name="timed">
        <flow><environment id="render" name="browser" action="open"
          timeout="0.01" retries="1" retry-delay="0" /></flow>
      </workflow>
    """)
    run = await runtime.run(definition, ctx=SimpleNamespace(workspace_root=str(tmp_path)))
    assert run.state == WorkflowState.FAILED
    assert runtime.kinds == [definition.program[0].type, definition.program[0].type]
    invocation = next(iter(run.invocations.values()))
    assert len(invocation.attempts) == 2


@pytest.mark.asyncio
async def test_frame_hierarchy_and_checkpoint_program_identity(tmp_path):
    def handler(target, task, args):
        if "items" in args:
            return {"data": {"count": len(args["items"])}}
        return {"ok": True}

    runtime = FakeRuntime(handler)
    definition = workflow_compiler.compile(HTML)
    run = await runtime.run(
        definition, input={"files": ["a.py", "b.py"]},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert run.successful
    assert all(
        frame.parent_key is None or frame.parent_key in run.frames
        for frame in run.frames.values()
    )
    changed = workflow_compiler.compile(HTML.replace("Summarize", "Summarize differently"))
    with pytest.raises(ValueError, match="executable contract"):
        await runtime.resume(changed, run.checkpoint_path, ctx=SimpleNamespace(workspace_root=str(tmp_path)))
    assert runtime.list_runs(definition.name)[0].id == run.id
    assert runtime.discard_run(run.id)
    assert runtime.get_run(run.id) is None


@pytest.mark.asyncio
async def test_background_start_is_immediately_visible_and_cleanup_releases_state(tmp_path):
    entered = asyncio.Event()

    async def wait_forever(*_):
        entered.set()
        await asyncio.Event().wait()

    runtime = FakeRuntime(wait_forever)
    definition = workflow_compiler.compile('<workflow name="background"><flow><agent name="worker" /></flow></workflow>')
    run_id = runtime.start(definition, ctx=SimpleNamespace(workspace_root=str(tmp_path)))
    assert runtime.get_run(run_id).state == WorkflowState.CREATED
    await asyncio.wait_for(entered.wait(), timeout=1)
    await runtime.cleanup()
    assert runtime.get_run(run_id) is None


@pytest.mark.asyncio
async def test_preflight_rejects_recursive_workflow_graph(tmp_path):
    first = workflow_manager.register(
        '<workflow name="cycle_a"><flow><workflow name="cycle_b" /></flow></workflow>',
        override=True,
    )
    workflow_manager.register(
        '<workflow name="cycle_b"><flow><workflow name="cycle_a" /></flow></workflow>',
        override=True,
    )
    try:
        run = await WorkflowRuntime().run(
            first, ctx=SimpleNamespace(workspace_root=str(tmp_path)),
        )
        assert run.state == WorkflowState.REJECTED
        assert "Recursive Workflow invocation" in run.error
    finally:
        workflow_manager.unregister("cycle_a")
        workflow_manager.unregister("cycle_b")


@pytest.mark.asyncio
async def test_nested_workflows_share_root_agent_budget(tmp_path):
    child = workflow_compiler.compile("""
      <workflow name="budget_child" max-agents="10">
        <flow>
          <agent id="one" name="worker" />
          <agent id="two" name="worker" />
        </flow>
      </workflow>
    """)
    parent = workflow_compiler.compile("""
      <workflow name="budget_parent" max-agents="2">
        <flow>
          <agent id="root_agent" name="worker" />
          <workflow id="nested" name="budget_child" />
        </flow>
      </workflow>
    """)

    class NestedRuntime(FakeRuntime):
        async def _invoke(self, kind, target, task, args, ctx, depth, budget=None):
            if kind.value == "workflow":
                return await self.run(child, input=args, ctx=ctx, depth=depth + 1, _budget=budget)
            return await super()._invoke(kind, target, task, args, ctx, depth, budget=budget)

    run = await NestedRuntime(lambda *_: {"ok": True}).run(
        parent, ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert run.state == WorkflowState.FAILED
    assert "Agent budget" in run.error


@pytest.mark.asyncio
async def test_validation_rejection_retry_attempts_and_skipped_branch(tmp_path):
    rejected = await FakeRuntime(lambda *_: None).run(
        workflow_compiler.compile(HTML), input={},
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    assert rejected.state == WorkflowState.REJECTED

    attempts = 0
    source = """
    <workflow name="retry">
      <flow>
        <agent id="unstable" name="worker" retries="1" />
        <branch id="choice" test="${unstable.data.ok}">
          <then><agent id="chosen" name="worker" /></then>
          <else><agent id="not_chosen" name="worker" /></else>
        </branch>
      </flow>
    </workflow>
    """
    def handler(target, task, args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return {"data": {"ok": True}}
    run = await FakeRuntime(handler).run(
        workflow_compiler.compile(source),
        ctx=SimpleNamespace(workspace_root=str(tmp_path)),
    )
    unstable = next(item for item in run.invocations.values() if item.key.endswith(":unstable"))
    assert [item.state for item in unstable.attempts] == [InvocationState.RETRYING, InvocationState.COMPLETED]
    assert any(frame.state == ExecutionState.SKIPPED for frame in run.frames.values())


def test_live_workflow_evaluation_summary():
    definition = workflow_manager.register(
        HTML.replace('name="dynamic_audit"', 'name="evaluated_workflow"'),
        override=True,
    )
    try:
        for index in range(3):
            retain_successful_run(definition, str(index))
            workflow_manager.record_evaluation(WorkflowEvaluation(
                workflow_name=definition.name, workflow_version=definition.version,
                run_id=str(index), success=True, quality_score=0.9,
            ))
        summary = workflow_manager.evaluation_summary(definition.name)
        assert summary["healthy"] is True
        assert definition.status == WorkflowStatus.ACTIVE
    finally:
        for index in range(3):
            workflow_runtime._runs.pop(str(index), None)
        workflow_manager.unregister(definition.name)


@pytest.mark.asyncio
async def test_workflow_roster_and_inspection_are_progressive():
    from autogenesis.tool.default.inspect_workflow import InspectWorkflow

    definition = workflow_manager.register(HTML, override=True)
    try:
        roster = workflow_manager.get_instruction()
        assert definition.name in roster
        assert "<workflow" not in roster

        response = await InspectWorkflow()(name=definition.name)
        assert response.success
        assert response.data["html"].lstrip().startswith("<workflow")
        assert response.data["nodes"][0]["type"] == "map"
        assert response.data["source_path"] is None
    finally:
        workflow_manager.unregister(definition.name)


def test_evaluation_evidence_is_version_scoped():
    v1 = workflow_manager.register(
        HTML.replace('name="dynamic_audit"', 'name="version_scoped"'),
        override=True,
    )
    try:
        for index in range(3):
            retain_successful_run(v1, f"v1-{index}")
            workflow_manager.record_evaluation(WorkflowEvaluation(
                workflow_name=v1.name, workflow_version=v1.version,
                run_id=f"v1-{index}", success=True, quality_score=1.0,
            ))
        v2 = workflow_manager.register(
            HTML.replace('name="dynamic_audit"', 'name="version_scoped"')
                .replace('version="1.2.0"', 'version="1.3.0"'),
            override=True,
        )
        assert workflow_manager.evaluation_summary(v2.name)["runs"] == 0
    finally:
        for index in range(3):
            workflow_runtime._runs.pop(f"v1-{index}", None)
        workflow_manager.unregister("version_scoped")


def test_evaluation_requires_real_unique_run_evidence():
    definition = workflow_manager.register(
        HTML.replace('name="dynamic_audit"', 'name="trusted_evidence"'), override=True,
    )
    try:
        with pytest.raises(ValueError, match="real Workflow run_id"):
            workflow_manager.record_evaluation(WorkflowEvaluation(
                workflow_name=definition.name, workflow_version=definition.version,
                success=True, quality_score=1.0,
            ))
        retain_successful_run(definition, "trusted-run", token_cost=25)
        evidence = WorkflowEvaluation(
            workflow_name=definition.name, workflow_version=definition.version,
            run_id="trusted-run", success=True, quality_score=1.0, token_cost=999,
        )
        recorded = workflow_manager.record_evaluation(evidence)
        assert recorded.case_id == "trusted-run"
        assert recorded.elapsed_ms == 1000
        assert recorded.token_cost == 25
        with pytest.raises(ValueError, match="already been evaluated"):
            workflow_manager.record_evaluation(evidence)
    finally:
        workflow_runtime._runs.pop("trusted-run", None)
        workflow_manager.unregister(definition.name)


def test_workflow_evaluator_has_narrow_execution_access():
    from autogenesis.agent.evaluator.workflow_evaluate_agent import WorkflowEvaluateAgent

    evaluator = WorkflowEvaluateAgent(base_dir=".")
    assert evaluator._include_agents() is False
    assert evaluator._include_workflows() is True
    assert evaluator._target_capability_allowlists("parallel_review") == {
        "workflow_allowlist": ["parallel_review"],
    }
    assert evaluator.permission_mode == "read_only"
    assert evaluator._allow_read_only_tool_call(
        "evolution_tool", {"action": "record_workflow_evaluation"},
    )
    assert not evaluator._allow_read_only_tool_call(
        "evolution_tool", {"action": "rollback"},
    )


def test_registration_hook_resolves_structured_or_quoted_paths(tmp_path):
    from autogenesis.hook.default.workflow_registration import WorkflowRegistrationHook

    directory = tmp_path / "workflow files"
    directory.mkdir()
    artifact = directory / "review workflow.html"
    artifact.write_text("<workflow name='review'><flow><checkpoint /></flow></workflow>")
    assert WorkflowRegistrationHook._resolve(
        None, str(artifact), "", str(tmp_path),
    ) == str(artifact)
    assert WorkflowRegistrationHook._resolve(
        None, None, f"created `{artifact}`", str(tmp_path),
    ) == str(artifact)
