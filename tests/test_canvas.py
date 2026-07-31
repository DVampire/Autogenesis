"""Canvas module: graph compilation, the reuse library, drafts, runs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from autogenesis.canvas.compiler import CanvasCompileError, canvas_compiler
from autogenesis.canvas.server import CanvasManagerServer
from autogenesis.canvas.types import FlowGraph, GraphEdge, GraphNode, Position, workflow_name_for
from autogenesis.workflow.types import StepType


def _node(node_id: str, **kwargs) -> GraphNode:
    return GraphNode(id=node_id, **kwargs)


def _review_graph(name: str = "Canvas review") -> FlowGraph:
    """input(task) → map[agent] → reduce → output, mirroring parallel_review."""
    return FlowGraph(
        name=name,
        nodes=[
            _node("task_in", type="input", name="task", required=True, description="What to review."),
            _node("angles", type="input", name="angles", input_type="array", required=True),
            _node("reviews", step_type="map", attrs={"item_name": "angle", "concurrency": 4},
                  position=Position(x=0, y=100)),
            _node("review", step_type="agent", target="general_agent",
                  task="Review from the ${angle} angle: ${inputs.task}", parent="reviews"),
            _node("report", step_type="reduce", target="general_agent",
                  task="Merge the findings into one report.", position=Position(x=0, y=300)),
            _node("out", type="output", name="report", position=Position(x=0, y=400)),
        ],
        edges=[
            GraphEdge(id="e1", source="angles", target="reviews", param="items"),
            GraphEdge(id="e2", source="reviews", target="report", param="items"),
            GraphEdge(id="e3", source="report", target="out", param="value"),
        ],
    )


def test_compile_produces_valid_registered_workflow_shape() -> None:
    html, definition = canvas_compiler.compile(_review_graph())
    assert definition.name == "canvas_review"
    assert set(definition.inputs) == {"task", "angles"}
    assert definition.outputs == {"report": "${report}"}
    types = [step.type for step in definition.program]
    assert types == [StepType.MAP, StepType.REDUCE]
    map_step = definition.program[0]
    assert map_step.items == "${inputs.angles}"
    assert map_step.item_name == "angle"
    assert map_step.children[0].type == StepType.AGENT
    reduce_step = definition.program[1]
    assert reduce_step.items == "${reviews}"
    assert definition.enable_evolving is True  # republish must pass the evolvable gate
    assert 'generated-by" content="canvas"' in html


def test_catalog_ports_are_typed() -> None:
    from autogenesis.canvas.catalog import catalog

    specs = {spec.id: spec for spec in asyncio.run(catalog.build())}
    io_input = specs["io/input"]
    assert [(port.name, port.type) for port in io_input.outputs] == [("out", "any")]
    map_spec = specs["step/map"]
    assert [port.name for port in map_spec.inputs] == ["items"]
    assert map_spec.inputs[0].type == "list"
    # map fans out on ``item`` and collects on ``done``.
    assert [port.name for port in map_spec.outputs] == ["item", "done"]


def test_capability_nodes_expose_message_data_files_ports() -> None:
    from autogenesis.canvas.catalog import catalog

    agent = next((s for s in asyncio.run(catalog.build()) if s.category == "agent"), None)
    if agent is None:
        pytest.skip("no actor agents registered")
    out = {port.name: port.type for port in agent.outputs}
    assert out == {"message": "text", "data": "object", "files": "list", "out": "any"}


def test_typed_edge_compiles_to_sub_path() -> None:
    graph = FlowGraph(
        name="typed",
        nodes=[
            _node("ag", step_type="agent", target="general_agent", task="Answer"),
            _node("out", type="output", name="answer"),
        ],
        edges=[GraphEdge(id="e", source="ag", target="out", param="value", source_port="message")],
    )
    _, definition = canvas_compiler.compile(graph)
    # message output port → ${ag.message} sub-path (not the whole ${ag}).
    assert definition.outputs == {"answer": "${ag.message}"}


def test_out_port_compiles_to_whole_value() -> None:
    graph = FlowGraph(
        name="whole",
        nodes=[
            _node("ag", step_type="agent", target="general_agent", task="Answer"),
            _node("out", type="output", name="answer"),
        ],
        edges=[GraphEdge(id="e", source="ag", target="out", param="value", source_port="out")],
    )
    _, definition = canvas_compiler.compile(graph)
    assert definition.outputs == {"answer": "${ag}"}


def test_agent_mounts_compile_to_allowlist_args() -> None:
    graph = FlowGraph(
        name="mounted",
        nodes=[
            _node("q", type="input", name="q", required=True),
            _node("ag", step_type="agent", target="general_agent", task="Answer: ${inputs.q}",
                  mounts={"tools": ["bash_tool", "web_searcher_tool"], "skills": ["debug"], "connectors": []}),
            _node("out", type="output", name="answer"),
        ],
        edges=[GraphEdge(id="e", source="ag", target="out", param="value")],
    )
    _, definition = canvas_compiler.compile(graph)
    agent_step = next(step for step in definition.program if step.type == StepType.AGENT)
    # Non-empty selections become args; the empty one is omitted (agent keeps defaults).
    assert agent_step.args.get("tools") == "bash_tool,web_searcher_tool"
    assert agent_step.args.get("skills") == "debug"
    assert "connectors" not in agent_step.args


def test_runtime_lifts_agent_mounts_into_allowlists() -> None:
    from autogenesis.agent.types import AgentContext
    from autogenesis.workflow.runtime import workflow_runtime

    ctx = AgentContext(extra={"session_id": "s1"})
    payload = {"task": "hi", "tools": "bash_tool,web_searcher_tool", "skills": "debug", "connectors": ""}
    derived = workflow_runtime._apply_agent_mounts(payload, ctx)
    assert payload == {"task": "hi"}  # mount args popped
    assert derived.extra["tool_allowlist"] == ["bash_tool", "web_searcher_tool"]
    assert derived.extra["skill_allowlist"] == ["debug"]
    assert "connector_allowlist" not in derived.extra  # empty selection ignored
    assert "tool_allowlist" not in ctx.extra  # shared ctx untouched (parallel-safe)


def test_compile_branch_then_else_and_args() -> None:
    graph = FlowGraph(
        name="branchy",
        nodes=[
            _node("check", step_type="tool", target="bash_tool", args={"command": "echo hi"},
                  position=Position(y=0)),
            _node("gate", step_type="branch", attrs={"condition": "${check}"}, position=Position(y=100)),
            _node("yes", step_type="agent", target="general_agent", task="Proceed: ${check}",
                  parent="gate", slot="then"),
            _node("no", step_type="agent", target="general_agent", task="Stop.",
                  parent="gate", slot="else"),
        ],
        edges=[],
    )
    _, definition = canvas_compiler.compile(graph)
    branch = definition.program[1]
    assert branch.type == StepType.BRANCH and branch.condition == "${check}"
    assert [child.id for child in branch.children] == ["yes"]
    assert [child.id for child in branch.else_children] == ["no"]


def test_compile_orders_steps_by_references() -> None:
    graph = FlowGraph(
        name="ordering",
        nodes=[
            _node("second", step_type="agent", target="general_agent", task="Use ${first}",
                  position=Position(y=0)),
            _node("first", step_type="agent", target="general_agent", task="Start",
                  position=Position(y=500)),
        ],
    )
    _, definition = canvas_compiler.compile(graph)
    assert [step.id for step in definition.program] == ["first", "second"]


def test_compile_rejects_broken_graphs() -> None:
    with pytest.raises(CanvasCompileError, match="no capability"):
        canvas_compiler.compile(FlowGraph(name="x", nodes=[_node("a", step_type="tool")]))
    with pytest.raises(CanvasCompileError, match="no steps"):
        canvas_compiler.compile(FlowGraph(name="x", nodes=[_node("i", type="input", name="q")]))
    with pytest.raises(CanvasCompileError, match="both connected and set"):
        canvas_compiler.compile(FlowGraph(
            name="x",
            nodes=[
                _node("a", step_type="tool", target="bash_tool", args={"command": "echo hi"}),
                _node("b", step_type="tool", target="bash_tool", args={"command": "echo bye"}),
            ],
            edges=[GraphEdge(id="e", source="a", target="b", param="arg:command")],
        ))


def test_draft_persistence_is_session_scoped(tmp_path) -> None:
    manager = CanvasManagerServer()
    session_a, session_b = tmp_path / "a" / "canvas", tmp_path / "b" / "canvas"
    draft = FlowGraph(name="wip", nodes=[_node("a", step_type="tool")])  # no target yet: still saves
    saved = manager.save_flow(draft, session_a)
    assert saved.id.startswith("flow-") and not saved.published
    assert manager.get_flow(saved.id, session_a).nodes[0].step_type == "tool"
    # The other session sees no drafts (published flows are global, drafts are not).
    assert all(item["published"] for item in manager.list_flows(session_b))
    assert asyncio.run(manager.delete_flow(saved.id, session_a)) is True


def test_export_to_library_roundtrip(tmp_path, monkeypatch) -> None:
    """A draft exported to the library comes back as a fresh, unbound draft."""
    monkeypatch.setenv("AUTOGENESIS_EXTENSION_ROOT", str(tmp_path / "extension"))
    manager = CanvasManagerServer()
    flows = tmp_path / "session" / "canvas"
    graph = manager.save_flow(_review_graph(name="library roundtrip"), flows)
    name = workflow_name_for(graph)

    exported = asyncio.run(manager.export_to_library(graph.id, flows))
    assert exported["name"] == name and exported["in_library"]
    assert Path(exported["artifact"]) == tmp_path / "extension" / "canvas" / f"{name}.json"
    assert Path(exported["artifact"]).is_file()
    assert name in manager.list_library_names()
    assert any(item["name"] == "library roundtrip" for item in manager.list_library())

    reopened = manager.import_from_library(name)
    assert reopened.name == "library roundtrip"
    assert {node.id for node in reopened.nodes} == {node.id for node in graph.nodes}
    assert reopened.nodes[2].position == graph.nodes[2].position  # layout survives
    # Importing starts a new draft rather than aliasing the library copy.
    assert not reopened.id
    assert manager.save_flow(reopened, flows).id != graph.id

    assert asyncio.run(manager.delete_from_library(name)) is True
    assert name not in manager.list_library_names()


def test_draft_run_executes_on_workflow_runtime(tmp_path) -> None:
    async def run() -> None:
        from autogenesis.tool import tool_manager
        if "bash_tool" not in await tool_manager.list():
            pytest.skip("bash_tool is not registered in this environment")
        manager = CanvasManagerServer()
        graph = FlowGraph(
            name="draft run",
            nodes=[
                _node("say", step_type="tool", target="bash_tool", args={"command": "echo canvas-ok"}),
                _node("out", type="output", name="said"),
            ],
            edges=[GraphEdge(id="e", source="say", target="out", param="value")],
        )
        run_id = await manager.run_flow(graph)
        for _ in range(100):
            status = manager.run_status(run_id)
            if status["state"] in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)
        assert status["state"] == "succeeded", status.get("error")
        assert "canvas-ok" in str(status["output"])

    asyncio.run(run())
