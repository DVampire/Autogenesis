"""The data-pipeline capability types: plugins (datasource) + process + benchmark.

A ``plugin`` is a packaging unit surfaced on the canvas as a semantic
``datasource`` node; a ``process`` node is a pure transform; a ``benchmark`` node
evaluates. All three are workflow step types dispatched by ``workflow_runtime``,
and every one returns the canonical ``{message, data, files}`` envelope so nodes
compose across edges. These tests pin that wiring without touching the network.
"""

from __future__ import annotations

import pytest

from autogenesis.benchmark import benchmark_manager
from autogenesis.benchmark.types import Task
from autogenesis.data import data_manager
from autogenesis.plugins import FMPPlugin, Plugin, plugin_manager
from autogenesis.process import (
    DeriveReturnProcessor,
    FilterRowsProcessor,
    ParseJsonProcessor,
    SelectFieldsProcessor,
    SplitTextProcessor,
    TypeConvertProcessor,
    process_manager,
)
from autogenesis.response.types import Response, ResponseType
from autogenesis.workflow.compiler import WorkflowCompiler
from autogenesis.workflow.runtime import workflow_runtime
from autogenesis.workflow.types import StepType


class _StubSource(Plugin):
    """Deterministic data-source plugin standing in for a real provider."""

    name: str = "stub_source"
    description: str = "Fixed records for tests."
    type: str = "data_source"

    async def __call__(self, **kwargs) -> Response:
        return Response(
            type=ResponseType.TOOL, success=True, message="stub 2 rows",
            data={"records": [
                {"date": "2024-01-01", "close": 1.0, "volume": 10, "junk": "x"},
                {"date": "2024-01-02", "close": 2.0, "volume": 20, "junk": "y"},
            ]},
        )


def _pipeline_html(source: str) -> str:
    return f"""<html><body><workflow name="t" version="1.0.0"><flow>
      <datasource id="src" name="{source}"/>
      <process id="clean" name="select_fields">
        <arg name="records" value="${{src.data.records}}"/>
        <arg name="fields" value='["date","close"]'/>
      </process>
    </flow></workflow></body></html>"""


@pytest.mark.asyncio
async def test_default_capabilities_register() -> None:
    await plugin_manager.initialize()
    await process_manager.initialize()
    assert "yahoo" in await plugin_manager.list()
    assert "select_fields" in await process_manager.list()


@pytest.mark.asyncio
async def test_derive_return_and_filter_rows() -> None:
    rows = [{"d": "1", "close": 10.0}, {"d": "2", "close": 11.0}, {"d": "3", "close": 9.0}]
    derived = await DeriveReturnProcessor()(records=rows, field="close")
    returns = [r["return"] for r in derived.data["records"]]
    assert returns[0] is None and returns[1] == pytest.approx(0.1)

    # numeric string comparison value is coerced, so this filters numerically
    kept = await FilterRowsProcessor()(records=rows, field="close", op="gt", value="10")
    assert [r["close"] for r in kept.data["records"]] == [11.0]


@pytest.mark.asyncio
async def test_generic_text_processors() -> None:
    assert (await SplitTextProcessor()(text="a\nb\nc")).data["chunks"] == ["a", "b", "c"]
    assert (await ParseJsonProcessor()(text='[{"x": 1}]')).data["value"] == [{"x": 1}]
    # string "3.5" coerces through float → int
    assert (await TypeConvertProcessor()(value="3.5", to="int")).data["value"] == 3


@pytest.mark.asyncio
async def test_frozen_node_is_inlined_and_not_run() -> None:
    from autogenesis.canvas.compiler import canvas_compiler
    from autogenesis.canvas.types import FlowGraph, GraphEdge, GraphNode, Position

    await process_manager.initialize()
    frozen = {"message": "f", "data": {"records": [{"close": 1.0}, {"close": 2.0}]}, "files": None}
    graph = FlowGraph(name="F", nodes=[
        GraphNode(id="src", type="step", step_type="datasource", target="yahoo",
                  frozen=True, frozen_output=frozen, position=Position()),
        GraphNode(id="clean", type="step", step_type="process", target="select_fields",
                  args={"fields": '["close"]'}, position=Position(y=100)),
    ], edges=[GraphEdge(id="e1", source="src", target="clean", param="arg:records", source_port="data")])

    html, definition = canvas_compiler.compile(graph)
    assert "<datasource" not in html  # the frozen node's step is dropped
    run = await workflow_runtime.run(definition)
    assert run.successful, run.error
    # only the process step ran — the frozen datasource was inlined, not executed
    assert list(run.invocations.keys()) == ["root.0:clean"]
    assert run.invocations["root.0:clean"].output["data"]["records"] == [{"close": 1.0}, {"close": 2.0}]


@pytest.mark.asyncio
async def test_knowledge_ingest_then_retrieve(tmp_path) -> None:
    from autogenesis.knowledge import knowledge_manager

    # Keep the ingested base out of the project tree.
    await knowledge_manager.initialize(base_dir=str(tmp_path / "knowledge"))
    assert set(await knowledge_manager.list_types()) >= {"bm25", "tfidf"}
    docs = [{"text": "The cat sat on the mat."}, {"text": "Python is a programming language."}]
    ingested = await knowledge_manager(name="knowledge_ingest",
                                       input={"base": "pytest_kb", "type": "bm25", "documents": docs})
    assert ingested.success
    hit = await knowledge_manager(name="knowledge_retrieve",
                                  input={"base": "pytest_kb", "query": "a cat on the mat", "top_k": 1})
    assert hit.success, hit.message
    # the most relevant document is retrieved first
    assert hit.data["records"][0]["text"] == "The cat sat on the mat."


@pytest.mark.asyncio
async def test_table_operations_group_by() -> None:
    from autogenesis.process import TableOperationsProcessor
    rows = [{"sym": "A", "px": 10.0}, {"sym": "A", "px": 12.0}, {"sym": "B", "px": 6.0}]
    result = await TableOperationsProcessor()(records=rows, operation="group_by", by="sym", column="px", agg="mean")
    grouped = {r["sym"]: r["px"] for r in result.data["records"]}
    assert grouped == {"A": 11.0, "B": 6.0}


@pytest.mark.asyncio
async def test_fmp_requires_key() -> None:
    # No key configured / no FMP_API_KEY → a graceful failed Response, not a crash.
    result = await FMPPlugin()(symbol="AAPL", api_key="")
    assert not result.success and "key" in result.message.lower()


@pytest.mark.asyncio
async def test_select_fields_coerces_json_string_fields() -> None:
    rows = [{"date": "d", "close": 1.0, "junk": "x"}]
    # fields arrives as a JSON string (how list ports compile), not a real list.
    result = await SelectFieldsProcessor()(records=rows, fields='["date","close"]')
    assert result.success
    assert result.data["records"] == [{"date": "d", "close": 1.0}]


def test_compiler_accepts_pipeline_tags() -> None:
    src = """<html><body><workflow name="t" version="1.0.0"><flow>
      <datasource id="a" name="yahoo"/>
      <process id="b" name="select_fields"/>
      <benchmark id="c" name="gsm8k"/>
    </flow></workflow></body></html>"""
    definition = WorkflowCompiler().compile(src)
    kinds = {step.id: step.type for step in definition.program}
    assert kinds == {"a": StepType.DATASOURCE, "b": StepType.PROCESS, "c": StepType.BENCHMARK}


@pytest.mark.asyncio
async def test_runtime_runs_datasource_to_process() -> None:
    await plugin_manager.initialize()
    await process_manager.initialize()
    await plugin_manager.register(_StubSource(), override=True)

    definition = WorkflowCompiler().compile(_pipeline_html("stub_source"))
    run = await workflow_runtime.run(definition)

    assert run.successful, run.error
    clean = run.invocations["root.1:clean"].output
    # The datasource's records crossed the ${src.data.records} edge and were
    # projected to exactly the selected fields.
    assert clean["data"]["records"] == [
        {"date": "2024-01-01", "close": 1.0},
        {"date": "2024-01-02", "close": 2.0},
    ]


@pytest.mark.asyncio
async def test_pipeline_saves_and_loads_dataset(tmp_path) -> None:
    await plugin_manager.initialize()
    await process_manager.initialize()
    await data_manager.initialize(base_dir=str(tmp_path / "datasets"))
    await plugin_manager.register(_StubSource(), override=True)

    # datasource → process → data(dataset_save, local), each edge over ${node.data}.
    # Local target uses the HuggingFace datasets format (save_to_disk) — offline,
    # no token, so it exercises the unified format without hitting the Hub.
    src = """<html><body><workflow name="t" version="1.0.0"><flow>
      <datasource id="src" name="stub_source"/>
      <process id="clean" name="select_fields">
        <arg name="records" value="${src.data}"/>
        <arg name="fields" value='["date","close"]'/>
      </process>
      <data id="save" name="dataset_save">
        <arg name="repo" value="pytest_pipeline_ds"/>
        <arg name="target" value="local"/>
        <arg name="records" value="${clean.data}"/>
      </data>
    </flow></workflow></body></html>"""
    run = await workflow_runtime.run(WorkflowCompiler().compile(src))
    assert run.successful, run.error

    # The saved HF dataset reads back as exactly the processed records.
    loaded = await data_manager(name="dataset_load", input={"repo": "pytest_pipeline_ds", "source": "local"})
    assert loaded.success, loaded.message
    assert loaded.data["records"] == [
        {"date": "2024-01-01", "close": 1.0},
        {"date": "2024-01-02", "close": 2.0},
    ]


def test_task_input_is_optional() -> None:
    # Regression: benchmark_manager.__call__ builds a Task without `input`, so it
    # must be optional or every evaluation silently scores 0.
    task = Task(task_id="1", result="5", ground_truth="5")
    assert task.input == ""


class _PredSource(Plugin):
    """A source of prediction/ground-truth records for the eval pipeline."""

    name: str = "pred_source"
    type: str = "data_source"

    async def __call__(self, **kwargs) -> Response:
        return Response(type=ResponseType.TOOL, success=True, message="2 preds",
                        data={"records": [{"p": 5, "g": 5}, {"p": 3, "g": 4}]})


@pytest.mark.asyncio
async def test_benchmark_pipeline_scores_predictions() -> None:
    await plugin_manager.initialize()
    await process_manager.initialize()
    await benchmark_manager.initialize(benchmark_names=["exact_match"])
    await plugin_manager.register(_PredSource(), override=True)

    # datasource → to_eval_records → benchmark(exact_match): 1 of 2 correct → 0.5.
    src = """<html><body><workflow name="t" version="1.0.0"><flow>
      <datasource id="src" name="pred_source"/>
      <process id="shape" name="to_eval_records">
        <arg name="records" value="${src.data}"/>
        <arg name="prediction_field" value="p"/>
        <arg name="ground_truth_field" value="g"/>
      </process>
      <benchmark id="score" name="exact_match">
        <arg name="results" value="${shape.data}"/>
      </benchmark>
    </flow></workflow></body></html>"""
    run = await workflow_runtime.run(WorkflowCompiler().compile(src))
    assert run.successful, run.error
    assert run.invocations["root.2:score"].output["data"]["score"] == 0.5
