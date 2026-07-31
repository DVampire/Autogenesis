"""Regression tests for the mailbox runtime's public contract."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from autogenesis.runtime import AgentDeadError, AgentStatus, TaskMessage, runtime_manager


class StubAgent:
    """Small protocol-compatible agent without importing the LLM stack."""

    name = "stub"

    def __init__(self, *, delay: float = 0, fail_on: str | None = None) -> None:
        self.delay = delay
        self.fail_on = fail_on

    async def handle(self, msg: Any, ref: Any) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if msg.task == self.fail_on:
            msg.reply_future.set_exception(ValueError("boom"))
            return
        msg.reply_future.set_result({"task": msg.task, "kwargs": msg.kwargs, "ref": ref.name})


def run(coro):
    return asyncio.run(coro)


def test_invoke_cleans_up_and_forwards_context() -> None:
    async def check() -> None:
        result = await runtime_manager.invoke(
            StubAgent(), name="one-shot", task="hello", parent_ref="parent", ctx={"id": "ctx"}
        )
        assert result == {
            "task": "hello",
            "kwargs": {"parent_ref": "parent", "ctx": {"id": "ctx"}},
            "ref": "one-shot",
        }
        assert runtime_manager.get("one-shot") is None

    run(check())


def test_spawn_ask_stop_lifecycle() -> None:
    async def check() -> None:
        ref = await runtime_manager.spawn(StubAgent(), name="lifecycle")
        assert ref.status is AgentStatus.RUNNING
        result = await runtime_manager.ask(ref, TaskMessage(task="ping"))
        assert result["task"] == "ping"
        await runtime_manager.stop(ref)
        assert ref.status is AgentStatus.STOPPED
        assert runtime_manager.get(ref.name) is None
        with pytest.raises(AgentDeadError):
            await runtime_manager.send(ref, TaskMessage(task="ghost"))

    run(check())


def test_spawn_name_collision() -> None:
    async def check() -> None:
        ref = await runtime_manager.spawn(StubAgent(), name="duplicate")
        try:
            with pytest.raises(ValueError, match="collision"):
                await runtime_manager.spawn(StubAgent(), name="duplicate")
        finally:
            await runtime_manager.stop(ref)

    run(check())


def test_ask_timeout_does_not_leak_runtime_ref() -> None:
    async def check() -> None:
        ref = await runtime_manager.spawn(StubAgent(delay=0.2), name="slow")
        with pytest.raises(asyncio.TimeoutError):
            await runtime_manager.ask(ref, TaskMessage(task="wait"), timeout=0.01)
        await asyncio.sleep(0.25)
        assert ref.status is AgentStatus.RUNNING
        assert (await runtime_manager.ask(ref, TaskMessage(task="next")))["task"] == "next"
        await runtime_manager.stop(ref)
        assert runtime_manager.get(ref.name) is None

    run(check())


def test_task_failure_does_not_kill_pump() -> None:
    async def check() -> None:
        ref = await runtime_manager.spawn(StubAgent(fail_on="boom"), name="resilient")
        try:
            with pytest.raises(ValueError, match="boom"):
                await runtime_manager.ask(ref, TaskMessage(task="boom"))
            assert ref.status is AgentStatus.RUNNING
            assert (await runtime_manager.ask(ref, TaskMessage(task="ok")))["task"] == "ok"
        finally:
            await runtime_manager.stop(ref)

    run(check())


def test_shutdown_clears_refs_and_repr_is_compact() -> None:
    async def check() -> None:
        first = await runtime_manager.spawn(StubAgent(), name="shutdown-a")
        await runtime_manager.spawn(StubAgent(), name="shutdown-b")
        assert "name='shutdown-a'" in repr(first)
        assert "running" in repr(first)
        await runtime_manager.shutdown()
        assert runtime_manager.list() == []

    run(check())
