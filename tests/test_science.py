"""The Science workstation: notebooks, compute, and the shared kernel.

Kernel execution itself needs a live Jupyter Server, so it is verified by hand
against the built image. What is pinned here is everything that answers without
one, plus the conversions that quietly lose data when they are wrong.
"""

from __future__ import annotations

import asyncio
import json

from autogenesis.gateway.protocol import GatewayCommand
from autogenesis.gateway.service import AgentGateway
from autogenesis.kernel import Execution, KernelOutput, kernel_manager
from autogenesis.paths import P, path_manager
from autogenesis.science import science_manager


def test_notebooks_are_workspace_files_not_kernel_state() -> None:
    """They list before a kernel exists and after it is gone.

    A notebook is a file in the project's workspace; the Jupyter Server is not.
    If this read went through the server, opening the Science view would show an
    empty list until one had booted.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]
        gateway._sessions[session_id].sandbox.materialize()  # noqa: SLF001

        listed = await gateway.handle(GatewayCommand(
            id="n", method="science.notebooks", params={"session_id": session_id}))
        assert listed.result["notebooks"] == []

        workspace = path_manager.get(P.SESSION_WORKSPACE, owner="local", session_id=session_id)
        (workspace / "analysis.ipynb").write_text(json.dumps({
            "cells": [{"cell_type": "code", "source": "1+1", "outputs": []}],
            "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        }), encoding="utf-8")

        listed = await gateway.handle(GatewayCommand(
            id="n2", method="science.notebooks", params={"session_id": session_id}))
        assert [(item["title"], item["cell_count"]) for item in listed.result["notebooks"]] == [("analysis", 1)]

    asyncio.run(run())


def test_the_history_is_saved_as_a_real_notebook() -> None:
    """The panel is the kernel's live history; this is how a run is kept.

    It has to come out as valid nbformat, or the thing you saved does not open
    in the JupyterLab sitting one button away.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]
        gateway._sessions[session_id].sandbox.materialize()  # noqa: SLF001

        # Stands in for a live kernel: what is under test is the conversion, not
        # the execution that produced it.
        kernel_manager._projects[session_id] = _FakeProject([  # noqa: SLF001
            Execution(execution_count=1, code="import torch", origin="agent",
                      outputs=[KernelOutput(type="stream", name="stdout", data={"text/plain": "ok\n"})]),
            Execution(execution_count=2, code="plt.plot(xs)", origin="user",
                      outputs=[KernelOutput(type="display", data={
                          "image/png": "iVBORw0KGgo=", "text/plain": "<Figure>"})]),
            Execution(execution_count=3, code="1/0", origin="agent", success=False,
                      error="Traceback...\nZeroDivisionError: division by zero",
                      outputs=[KernelOutput(type="error", data={
                          "text/plain": "Traceback...\nZeroDivisionError: division by zero"})]),
        ])
        try:
            saved = await gateway.handle(GatewayCommand(
                id="s", method="science.save", params={"session_id": session_id, "name": "run"}))
            path = saved.result["notebook"]["path"]
            workspace = path_manager.get(P.SESSION_WORKSPACE, owner="local", session_id=session_id)
            document = json.loads((workspace / path).read_text(encoding="utf-8"))
        finally:
            kernel_manager._projects.pop(session_id, None)  # noqa: SLF001

        assert document["nbformat"] == 4 and len(document["cells"]) == 3
        kinds = [output["output_type"] for cell in document["cells"] for output in cell["outputs"]]
        assert kinds == ["stream", "display_data", "error"]
        # The figure survives: a plot that becomes a string on save is a plot lost.
        assert document["cells"][1]["outputs"][0]["data"]["image/png"] == "iVBORw0KGgo="
        # nbformat needs all three error fields; only a traceback was carried.
        error = document["cells"][2]["outputs"][0]
        assert error["ename"] == "ZeroDivisionError" and error["evalue"] == "division by zero"
        # Who ran what is kept — seeing what the AGENT ran is most of the point.
        assert [cell["metadata"]["autogenesis"]["origin"] for cell in document["cells"]] == \
            ["agent", "user", "agent"]

    asyncio.run(run())


def test_a_machine_without_gpus_reports_none_rather_than_failing() -> None:
    """Plenty of hosts have no NVIDIA card, so the panel says so instead of
    showing a meter with nothing behind it."""
    import autogenesis.science.server as module

    original = module.shutil.which
    try:
        module.shutil.which = lambda name: None if name == "nvidia-smi" else original(name)
        assert module._gpu_status() == []  # noqa: SLF001
    finally:
        module.shutil.which = original


def test_compute_answers_before_a_kernel_has_started() -> None:
    """Opening the view must not depend on having run something first."""

    async def run() -> None:
        status = await science_manager.compute("no-such-project")
        assert status.running is False and status.executions == 0
        # The machine's own numbers are readable regardless.
        assert status.cpu_count and status.cpu_count > 0

    asyncio.run(run())


def test_the_lab_is_served_under_the_projects_own_path() -> None:
    """Which is what lets the UI host it on whatever origin the browser used."""
    from autogenesis.science import base_path

    assert base_path("abc123") == "/science/abc123"


class _FakeProject:
    """Just enough of a kernel project for the history conversions."""

    def __init__(self, history) -> None:
        self.history = history
        self.busy = False
        self.workspace = ""


def test_the_history_poll_only_sends_what_is_new() -> None:
    """A history holding a few figures is megabytes of base64.

    The panel polls while the agent works, so resending all of it every few
    seconds would be pure waste — ``after`` is the client's cursor.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]

        kernel_manager._projects[session_id] = _FakeProject([  # noqa: SLF001
            Execution(execution_count=n, code=f"step {n}", origin="agent") for n in (1, 2, 3)
        ])
        try:
            first = await gateway.handle(GatewayCommand(
                id="h1", method="science.history", params={"session_id": session_id}))
            assert first.result["total"] == 3
            assert [item["code"] for item in first.result["executions"]] == ["step 1", "step 2", "step 3"]

            # Nothing new: the poll costs a status, not the whole transcript.
            second = await gateway.handle(GatewayCommand(
                id="h2", method="science.history", params={"session_id": session_id, "after": 3}))
            assert second.result["executions"] == [] and second.result["total"] == 3

            kernel_manager._projects[session_id].history.append(  # noqa: SLF001
                Execution(execution_count=4, code="step 4", origin="user"))
            third = await gateway.handle(GatewayCommand(
                id="h3", method="science.history", params={"session_id": session_id, "after": 3}))
            assert [item["code"] for item in third.result["executions"]] == ["step 4"]
        finally:
            kernel_manager._projects.pop(session_id, None)  # noqa: SLF001

    asyncio.run(run())


def test_the_gpu_reading_is_sampled_in_the_background_not_per_request() -> None:
    """nvidia-smi takes ~0.5s on a loaded machine.

    Reading it inside the request made every poll wait for it, and two open tabs
    paid for it twice — on an async gateway that half second is half a second of
    not streaming the agent's reply.
    """

    async def run() -> None:
        import autogenesis.science.server as module

        calls = []

        def counted():
            calls.append(1)
            return [{"index": 0, "name": "Fake", "memory_used_mb": 1,
                     "memory_total_mb": 2, "utilization_percent": 3}]

        manager = module.ScienceManagerServer()
        original, module._gpu_status = module._gpu_status, counted  # noqa: SLF001
        try:
            first = await manager.gpus()
            for _ in range(5):
                assert await manager.gpus() == first
            # One sample served six reads.
            assert len(calls) == 1
        finally:
            module._gpu_status = original  # noqa: SLF001
            await manager.stop_all()

    asyncio.run(run())


def test_the_reaper_never_closes_a_server_whose_kernel_is_working() -> None:
    """Time alone would kill a training run.

    A long computation holds the kernel for hours with nobody watching, so an
    idle clock says "gone" while the work is very much alive. The science
    container's reaper did exactly this; the replacement asks the server what
    its kernel is actually doing before closing anything.
    """

    async def run() -> None:
        import time

        import autogenesis.kernel.server as module

        manager = module.KernelManagerServer()
        stale = time.time() - module.IDLE_TIMEOUT_SECONDS - 60
        quiet = module._Project(key="quiet", workspace="/tmp", kernel_id="k1",  # noqa: SLF001
                                base_url="http://127.0.0.1:1/x", last_seen=stale)
        working = module._Project(key="training", workspace="/tmp", kernel_id="k2",  # noqa: SLF001
                                  base_url="http://127.0.0.1:2/x", last_seen=stale)
        manager._projects.update({"quiet": quiet, "training": working})  # noqa: SLF001

        closed: list[str] = []

        async def shutdown(key):
            closed.append(key)
            manager._projects.pop(key, None)  # noqa: SLF001
            return True

        async def kernel_is_busy(project):
            return project.key == "training"

        # Patched on the INSTANCE, not the class: patching the class would leak
        # into every later test in the session.
        manager.shutdown = shutdown  # type: ignore[method-assign]
        manager._kernel_is_busy = kernel_is_busy  # type: ignore[method-assign]  # noqa: SLF001
        original, module.REAP_INTERVAL_SECONDS = module.REAP_INTERVAL_SECONDS, 0.01
        try:
            manager._ensure_reaper()  # noqa: SLF001
            await asyncio.sleep(0.15)
        finally:
            module.REAP_INTERVAL_SECONDS = original
            if manager._reaper:  # noqa: SLF001
                manager._reaper.cancel()  # noqa: SLF001

        assert closed == ["quiet"], "the working kernel must survive"
        # And its clock moved forward, so it is not re-checked every pass for
        # the whole length of the run.
        assert working.last_seen > stale

    asyncio.run(run())
