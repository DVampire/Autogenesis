"""Focused tests for the interactive Gateway's protocol-only behavior."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autogenesis.gateway.protocol import GatewayCommand, PROTOCOL_VERSION
from autogenesis.gateway.service import AgentGateway
from autogenesis.model import model_manager
from autogenesis.canvas.types import FlowGraph, GraphNode
from autogenesis.model.types import ModelConfig


async def _test_event_ordering_and_replay() -> None:
    gateway = AgentGateway(event_history_size=10)
    queue = await gateway.subscribe()

    created = await gateway.handle(
        GatewayCommand(id="create", method="session.create", params={})
    )
    assert created.ok
    session_id = created.result["session_id"]
    assert isinstance(session_id, str)

    first = await queue.get()
    assert first.type == "session.created"
    assert first.seq_no == 1

    await gateway._publish("agent.progress", {"step": 1}, session_id=session_id)
    second = await queue.get()
    assert second.seq_no == 2

    replay = await gateway.handle(
        GatewayCommand(
            id="replay",
            method="session.events",
            params={"session_id": session_id, "after_seq": 1},
        )
    )
    assert replay.ok
    assert [event["type"] for event in replay.result["events"]] == ["agent.progress"]
    gateway.unsubscribe(queue)


def test_event_ordering_and_replay() -> None:
    asyncio.run(_test_event_ordering_and_replay())


def test_rejects_unknown_protocol_version() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        response = await gateway.handle(
            GatewayCommand(
                id="old",
                method="hello",
                params={},
                protocol_version=PROTOCOL_VERSION + 1,
            )
        )
        assert not response.ok
        assert response.error is not None
        assert response.error.code == "unsupported_protocol"

    asyncio.run(run())


def test_session_capability_selection_is_persisted() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={})
        )
        assert created.ok
        session_id = created.result["session_id"]

        catalog = await gateway.handle(GatewayCommand(id="catalog", method="capability.list"))
        assert catalog.ok
        # capability.list returns descriptors ({type, name, source, evolving});
        # a selection is just the names.
        selection = {
            roster: [item["name"] for item in items[:1]]
            for roster, items in catalog.result.items()
            if isinstance(items, list)
        }
        updated = await gateway.handle(
            GatewayCommand(
                id="select",
                method="session.capabilities.set",
                params={"session_id": session_id, "capabilities": selection},
            )
        )
        assert updated.ok
        assert updated.result["capabilities"] == selection

        invalid = await gateway.handle(
            GatewayCommand(
                id="invalid",
                method="session.capabilities.set",
                params={
                    "session_id": session_id,
                    "capabilities": {**selection, "tools": ["not-a-real-tool"]},
                },
            )
        )
        assert not invalid.ok
        assert invalid.error is not None
        assert invalid.error.code == "invalid_request"

    asyncio.run(run())


def test_session_can_be_renamed() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={"name": "web"})
        )
        assert created.ok
        session_id = created.result["session_id"]

        renamed = await gateway.handle(
            GatewayCommand(
                id="rename",
                method="session.rename",
                params={"session_id": session_id, "name": "Review authentication flow"},
            )
        )
        assert renamed.ok
        assert renamed.result["name"] == "Review authentication flow"

        listed = await gateway.handle(GatewayCommand(id="list", method="session.list"))
        assert listed.ok
        assert listed.result["sessions"][0]["name"] == "Review authentication flow"

    asyncio.run(run())


def test_extension_capability_changes_update_live_sessions() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        catalog = {"agents": [], "tools": [], "skills": [], "connectors": []}

        async def available_capabilities() -> dict[str, list[str]]:
            return {kind: list(names) for kind, names in catalog.items()}

        gateway._available_capabilities = available_capabilities  # type: ignore[method-assign]
        queue = await gateway.subscribe()
        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={})
        )
        assert created.ok
        session_id = created.result["session_id"]
        await queue.get()

        catalog["tools"] = ["generated_tool"]
        await gateway._on_extension_change(
            {"action": "registered", "module": "tool", "name": "generated_tool", "version": "1.0.0"}
        )

        selection_event = await queue.get()
        catalog_event = await queue.get()
        assert selection_event.type == "session.capabilities.updated"
        assert selection_event.session_id == session_id
        assert selection_event.payload["capabilities"]["tools"] == ["generated_tool"]
        assert catalog_event.type == "capabilities.changed"
        assert catalog_event.payload["capabilities"]["tools"] == ["generated_tool"]
        gateway.unsubscribe(queue)

    asyncio.run(run())


def test_commands_are_exposed_and_execute_in_a_gateway_session() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        catalog = await gateway.handle(GatewayCommand(id="catalog", method="capability.list"))
        assert catalog.ok
        assert "commands" in catalog.result
        assert "environments" in catalog.result
        assert "inspect" in [item["name"] for item in catalog.result["commands"]]

        detail = await gateway.handle(
            GatewayCommand(id="detail", method="capability.get", params={"kind": "commands", "name": "inspect"})
        )
        assert detail.ok
        assert detail.result["usage"] == "/inspect <type> <name>"
        assert detail.result["language"] == "markdown"
        assert "## Examples" in detail.result["document"]
        assert "`/inspect tool bash_tool`" in detail.result["document"]

        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={})
        )
        assert created.ok
        executed = await gateway.handle(
            GatewayCommand(
                id="help",
                method="command.execute",
                params={"session_id": created.result["session_id"], "raw": "/help"},
            )
        )
        assert executed.ok
        assert executed.result["success"] is True
        assert "[control]" in executed.result["message"]

    asyncio.run(run())


def test_model_catalog_groups_models_without_credentials() -> None:
    async def run() -> None:
        models = model_manager.model_context_manager.models
        previous_models = dict(models)
        try:
            models.clear()
            models["openai/demo"] = ModelConfig(
                model_name="openai/demo",
                model_id="demo-1",
                model_type="chat/completions",
                provider="openai",
                api_key="must-not-be-exposed",
                supports_functions=True,
            )
            response = await AgentGateway().handle(GatewayCommand(id="models", method="model.list"))
            assert response.ok
            assert response.result["providers"] == [{
                "name": "openai",
                "models": [{
                    "name": "openai/demo",
                    "id": "demo-1",
                    "type": "chat/completions",
                    "streaming": True,
                    "functions": True,
                    "vision": False,
                }],
            }]
        finally:
            models.clear()
            models.update(previous_models)

    asyncio.run(run())


def test_model_configuration_is_editable_without_exposing_api_keys() -> None:
    async def run() -> None:
        models = model_manager.model_context_manager.models
        previous_models = dict(models)
        registered: list[ModelConfig] = []

        async def register_model(_, config: ModelConfig) -> None:
            registered.append(config)

        try:
            models.clear()
            models["openai/demo"] = ModelConfig(
                model_name="openai/demo",
                model_id="demo-1",
                model_type="chat/completions",
                provider="openai",
                api_key="must-not-be-exposed",
            )
            gateway = AgentGateway()
            detail = await gateway.handle(
                GatewayCommand(id="model-detail", method="model.get", params={"name": "openai/demo"})
            )
            assert detail.ok
            assert detail.result["has_api_key"] is True
            assert "api_key" not in detail.result["configuration"]

            with patch.object(type(model_manager), "register_model", register_model):
                updated = await gateway.handle(
                    GatewayCommand(
                        id="model-configure",
                        method="model.configure",
                        params={
                            "original_name": "openai/demo",
                            "configuration": {"temperature": 0.2},
                        },
                    )
                )
            assert updated.ok
            assert registered[0].api_key == "must-not-be-exposed"
            assert registered[0].temperature == 0.2
            assert "api_key" not in updated.result["configuration"]
        finally:
            models.clear()
            models.update(previous_models)

    asyncio.run(run())


def test_session_files_upload_in_chunks_and_can_be_removed() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={})
        )
        assert created.ok
        session_id = created.result["session_id"]

        content = b"<html><body>Agent task</body></html>"
        begun = await gateway.handle(
            GatewayCommand(
                id="begin",
                method="file.upload.begin",
                params={"session_id": session_id, "name": "task.html", "size": len(content), "mime_type": "text/html"},
            )
        )
        assert begun.ok
        file_id = begun.result["file"]["id"]
        chunk = await gateway.handle(
            GatewayCommand(
                id="chunk",
                method="file.upload.chunk",
                params={"session_id": session_id, "file_id": file_id, "data": base64.b64encode(content).decode()},
            )
        )
        assert chunk.ok
        completed = await gateway.handle(
            GatewayCommand(id="complete", method="file.upload.complete", params={"session_id": session_id, "file_id": file_id})
        )
        assert completed.ok
        path = completed.result["file"]["path"]
        assert open(path, "rb").read() == content

        listed = await gateway.handle(GatewayCommand(id="list", method="file.list", params={"session_id": session_id}))
        assert listed.ok
        assert [item["name"] for item in listed.result["files"]] == ["task.html"]

        removed = await gateway.handle(
            GatewayCommand(id="remove", method="file.remove", params={"session_id": session_id, "file_id": file_id})
        )
        assert removed.ok
        assert not Path(path).exists()

    asyncio.run(run())


def test_session_rejects_client_selected_project_root() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        response = await gateway.handle(
            GatewayCommand(
                id="create",
                method="session.create",
                params={"project_root": "/tmp/not-server-managed"},
            )
        )
        assert not response.ok
        assert response.error is not None
        assert response.error.code == "invalid_request"

    asyncio.run(run())


def test_gateway_keeps_session_workspace_empty_and_separate_from_source(tmp_path: Path) -> None:
    async def run() -> None:
        source = tmp_path / "source"
        source.mkdir()
        (source / "project.txt").write_text("original", encoding="utf-8")
        gateway = AgentGateway(workspace_source=source)
        created = await gateway.handle(
            GatewayCommand(
                id="create",
                method="session.create",
                params={"workspace": str(source)},
            )
        )
        assert created.ok
        workspace = Path(created.result["workspace"])
        assert workspace != source
        # The session sandbox is lazily materialized (ProjectSandbox.create(materialize=False)):
        # opening a session must leave no empty workspace directory behind — it is created
        # on first real use, not up front.
        assert not workspace.exists()
        assert created.result["source_workspace"] == str(source)

        listed = await gateway.handle(GatewayCommand(id="list", method="session.list"))
        assert listed.ok
        assert listed.result["sessions"][0]["source_workspace"] == str(source)

    asyncio.run(run())


def test_gateway_rejects_arbitrary_client_workspace(tmp_path: Path) -> None:
    async def run() -> None:
        source = tmp_path / "source"
        source.mkdir()
        gateway = AgentGateway()
        created = await gateway.handle(
            GatewayCommand(
                id="create",
                method="session.create",
                params={"workspace": str(source)},
            )
        )
        assert not created.ok
        assert created.error is not None
        assert created.error.code == "invalid_request"

    asyncio.run(run())


def test_workspace_browser_is_session_scoped_and_reads_text(tmp_path: Path) -> None:
    async def run() -> None:
        source = tmp_path / "source"
        source.mkdir()
        gateway = AgentGateway(workspace_source=source)
        created = await gateway.handle(GatewayCommand(id="create", method="session.create", params={}))
        session_id = created.result["session_id"]
        workspace = Path(created.result["workspace"])
        # Workspace is lazily materialized, so create the tree the way first real use would.
        (workspace / "src").mkdir(parents=True)
        (workspace / "src" / "app.py").write_text("print('sandbox')\n", encoding="utf-8")
        (workspace / ".secret").write_text("hidden", encoding="utf-8")

        tree = await gateway.handle(GatewayCommand(
            id="tree", method="workspace.tree", params={"session_id": session_id, "path": ""},
        ))
        assert tree.ok
        assert [entry["name"] for entry in tree.result["entries"]] == ["src"]

        nested = await gateway.handle(GatewayCommand(
            id="nested", method="workspace.tree", params={"session_id": session_id, "path": "src"},
        ))
        assert nested.result["entries"][0]["path"] == "src/app.py"

        opened = await gateway.handle(GatewayCommand(
            id="read", method="workspace.file.read",
            params={"session_id": session_id, "path": "src/app.py"},
        ))
        assert opened.ok
        assert opened.result["content"] == "print('sandbox')\n"
        assert opened.result["language"] == "python"
        assert len(opened.result["etag"]) == 64

        escaped = await gateway.handle(GatewayCommand(
            id="escape", method="workspace.file.read",
            params={"session_id": session_id, "path": "../source/.secret"},
        ))
        assert not escaped.ok
        assert escaped.error is not None
        assert escaped.error.code == "invalid_request"

    asyncio.run(run())


def test_session_exposes_staged_extension_sandbox() -> None:
    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(
            GatewayCommand(id="create", method="session.create", params={})
        )
        assert created.ok
        assert created.result["extension_root"] == str(Path(created.result["project_root"]) / "extension")

        stage = await gateway.handle(
            GatewayCommand(
                id="stage",
                method="extension.stage.get",
                params={"session_id": created.result["session_id"]},
            )
        )
        assert stage.ok
        assert stage.result["staging"]["valid"] is True
        assert stage.result["staging"]["components"] == []
        assert stage.result["mounts"][:2] == [
            {"source": str(Path(created.result["project_root"]) / "workspace"), "target": "/workspace", "mode": "rw"},
            {"source": str(Path(created.result["project_root"]) / "extension"), "target": "/extension", "mode": "rw"},
        ]

    asyncio.run(run())


def test_tool_and_agent_details_are_human_readable_guides() -> None:
    guide = AgentGateway._capability_usage_document(
        "tools",
        "example_tool",
        SimpleNamespace(description="Perform an example action.", instruction="Run this only when needed."),
    )
    assert "## What it does" in guide
    assert "## How to use it" in guide
    assert "Run this only when needed." in guide
    assert '"properties"' not in guide


def test_a_restarted_gateway_reopens_the_conversation() -> None:
    """A transcript is the record of what happened; a restart must not eat it.

    The in-memory buffer is bounded and dies with the process, so the
    conversation is read back from its file on disk instead.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        assert created.ok
        session_id = created.result["session_id"]

        # The project becomes real — the point at which it starts leaving a
        # record, the same rule the manifest beside it follows.
        session = gateway._sessions[session_id]  # noqa: SLF001
        session.sandbox.materialize()
        gateway._write_session_manifest(session)  # noqa: SLF001

        conversation = gateway._resolve_conversation(session, {"view": "chat"})  # noqa: SLF001
        await gateway._publish("task.submitted", {"content": "hi"},  # noqa: SLF001
                               session_id=session_id, conversation_id=conversation.id)

        before = await gateway.handle(GatewayCommand(
            id="e1", method="conversation.events",
            params={"session_id": session_id, "conversation_id": conversation.id}))
        assert before.ok and before.result["events"], "the conversation recorded nothing"

        # A fresh gateway over the same tree — the restart.
        restarted = AgentGateway()
        await restarted._restore_sessions()  # noqa: SLF001
        assert session_id in restarted._sessions  # noqa: SLF001

        listed = await restarted.handle(GatewayCommand(
            id="l", method="conversation.list", params={"session_id": session_id}))
        assert [item["conversation_id"] for item in listed.result["conversations"]] == [conversation.id]

        after = await restarted.handle(GatewayCommand(
            id="e2", method="conversation.events",
            params={"session_id": session_id, "conversation_id": conversation.id}))
        assert [event["type"] for event in after.result["events"]] == \
               [event["type"] for event in before.result["events"]]

        # New events continue the numbering rather than colliding with replayed ones.
        highest = max(event["seq_no"] for event in after.result["events"])
        restored_session = restarted._sessions[session_id]  # noqa: SLF001
        restarted._resolve_conversation(restored_session, {"conversation_id": conversation.id})  # noqa: SLF001
        published = await restarted._publish("test.marker", {}, session_id=session_id,  # noqa: SLF001
                                             conversation_id=conversation.id)
        assert published.seq_no > highest

    asyncio.run(run())


def test_two_conversations_in_one_project_stay_apart() -> None:
    """Their transcripts are separate, and so is the state keyed by ctx.id."""

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]
        session = gateway._sessions[session_id]  # noqa: SLF001
        session.sandbox.materialize()
        gateway._write_session_manifest(session)  # noqa: SLF001

        first = gateway._resolve_conversation(session, {"view": "chat"})  # noqa: SLF001
        second = gateway._resolve_conversation(session, {"view": "science"})  # noqa: SLF001
        assert first.id != second.id

        await gateway._publish("task.submitted", {"content": "one"},  # noqa: SLF001
                               session_id=session_id, conversation_id=first.id)
        await gateway._publish("task.submitted", {"content": "two"},  # noqa: SLF001
                               session_id=session_id, conversation_id=second.id)

        async def transcript(cid):
            response = await gateway.handle(GatewayCommand(
                id=f"e{cid}", method="conversation.events",
                params={"session_id": session_id, "conversation_id": cid}))
            return [event["payload"]["content"] for event in response.result["events"]]

        assert await transcript(first.id) == ["one"]
        assert await transcript(second.id) == ["two"]

        # A view can list only its own.
        science = await gateway.handle(GatewayCommand(
            id="ls", method="conversation.list", params={"session_id": session_id, "view": "science"}))
        assert [item["conversation_id"] for item in science.result["conversations"]] == [second.id]

    asyncio.run(run())


def test_canvas_run_history_outlives_the_runtime() -> None:
    """Reopening a flow shows what it did last, not an empty canvas."""

    async def run() -> None:
        from autogenesis.canvas.server import canvas_manager
        from autogenesis.paths import P, path_manager

        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]
        owner = gateway._sessions[session_id].owner  # noqa: SLF001

        flows = path_manager.get(P.SESSION_FLOWS, owner=owner, session_id=session_id)
        runs = path_manager.get(P.SESSION_RUNS, owner=owner, session_id=session_id)
        graph = canvas_manager.save_flow(
            FlowGraph(name="history", nodes=[GraphNode(id="a", type="step", step_type="tool", target="bash_tool")]),
            flows,
        )
        canvas_manager.record_run(graph.id, "run-one", runs)
        canvas_manager.record_run(graph.id, "run-two", runs)

        listed = await gateway.handle(GatewayCommand(
            id="l", method="canvas.run.list", params={"session_id": session_id, "flow_id": graph.id}))
        assert listed.ok
        # Newest first, and a run whose record is gone is reported, not hidden.
        assert [item["run_id"] for item in listed.result["runs"]] == ["run-two", "run-one"]
        assert {item["state"] for item in listed.result["runs"]} == {"unknown"}

    asyncio.run(run())


def test_an_older_project_keeps_its_transcript() -> None:
    """A project written before conversations existed must not lose its history.

    Its single events.jsonl would otherwise just stop being read — still on
    disk, with nothing able to open it.
    """

    async def run() -> None:
        from autogenesis.paths import P, path_manager

        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]
        session = gateway._sessions[session_id]  # noqa: SLF001
        session.sandbox.materialize()
        gateway._write_session_manifest(session)  # noqa: SLF001

        # A transcript in the old shape, beside the manifest.
        legacy = path_manager.get(P.SESSION, owner=session.owner, session_id=session_id) / "events.jsonl"
        legacy.write_text('{"type": "task.submitted", "seq_no": 1, "payload": {"content": "old work"}}\n',
                          encoding="utf-8")

        restarted = AgentGateway()
        await restarted._restore_sessions()  # noqa: SLF001

        listed = await restarted.handle(GatewayCommand(
            id="l", method="conversation.list", params={"session_id": session_id}))
        assert len(listed.result["conversations"]) == 1
        adopted = listed.result["conversations"][0]["conversation_id"]

        events = await restarted.handle(GatewayCommand(
            id="e", method="conversation.events",
            params={"session_id": session_id, "conversation_id": adopted}))
        assert [event["payload"]["content"] for event in events.result["events"]] == ["old work"]
        # The original is kept, renamed, so the rewrite is visible.
        assert not legacy.exists() and legacy.with_suffix(".jsonl.migrated").is_file()

    asyncio.run(run())


def test_a_project_is_named_by_what_was_first_asked_of_it() -> None:
    """And keeps that name — a later message must not rewrite the title.

    The list of past projects is only usable if the entries differ. They all
    used to read "web" or "Web session 10:23", which said nothing about which
    project was which.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(
            id="c", method="session.create", params={"name": "New project"}))
        session_id = created.result["session_id"]

        await gateway.handle(GatewayCommand(id="t1", method="task.submit", params={
            "session_id": session_id, "content": "Plot the revenue by quarter"}))
        await gateway.handle(GatewayCommand(id="t2", method="task.submit", params={
            "session_id": session_id, "content": "Now do it by region"}))

        listed = await gateway.handle(GatewayCommand(id="l", method="session.list", params={}))
        project = next(item for item in listed.result["sessions"] if item["session_id"] == session_id)
        assert project["name"] == "Plot the revenue by quarter"
        # The title survives a restart: it is in the manifest, not just in memory.
        restarted = AgentGateway()
        await restarted._restore_sessions()  # noqa: SLF001
        reopened = await restarted.handle(GatewayCommand(id="l2", method="session.list", params={}))
        assert next(item for item in reopened.result["sessions"]
                    if item["session_id"] == session_id)["name"] == "Plot the revenue by quarter"

    asyncio.run(run())


def test_projects_are_listed_most_recently_worked_in_first() -> None:
    """The list is how someone gets back to what they were doing."""

    async def run() -> None:
        gateway = AgentGateway()
        ids = []
        for content in ("first project", "second project", "third project"):
            created = await gateway.handle(GatewayCommand(id=f"c{content}", method="session.create", params={}))
            session_id = created.result["session_id"]
            ids.append(session_id)
            await gateway.handle(GatewayCommand(id=f"t{content}", method="task.submit", params={
                "session_id": session_id, "content": content}))

        # Touch the oldest again; it should climb to the top.
        await gateway.handle(GatewayCommand(id="again", method="task.submit", params={
            "session_id": ids[0], "content": "back to the first"}))

        # Asserting the whole order, not just the head: sessions are stored in
        # creation order, so "ids[0] is first" would also hold with no sorting
        # at all — the touched-oldest-climbs case is the one that discriminates.
        listed = await gateway.handle(GatewayCommand(id="l", method="session.list", params={}))
        assert [item["session_id"] for item in listed.result["sessions"]] == [ids[0], ids[2], ids[1]]

    asyncio.run(run())


def test_a_vnc_live_view_never_hands_the_client_the_raw_socket() -> None:
    """The client gets a same-origin path; the ephemeral target stays server-side.

    This broke silently once already: the field was renamed ``kind`` -> ``type``
    and the check kept reading ``kind``, so it matched nothing and every raw
    websockify address went straight out to the browser.
    """

    async def run() -> None:
        from autogenesis.environment.types import EnvironmentView

        gateway = AgentGateway()
        published: list = []

        async def capture(event_type, payload, **_) -> None:
            published.append((event_type, payload))

        gateway._publish = capture  # type: ignore[method-assign]  # noqa: SLF001

        await gateway._on_environment_view(EnvironmentView(  # noqa: SLF001
            env_name="browser", type="vnc", url="ws://172.17.0.5:41293/websockify"))
        assert published[-1][1]["url"] == "/env/vnc"
        assert gateway._latest_vnc_target == "ws://172.17.0.5:41293/websockify"  # noqa: SLF001

        # An iframe view is a plain page; it is passed through untouched.
        await gateway._on_environment_view(EnvironmentView(  # noqa: SLF001
            env_name="ide", type="iframe", url="http://localhost:8080/"))
        assert published[-1][1]["url"] == "http://localhost:8080/"

    asyncio.run(run())


def test_an_untouched_session_is_listed_but_marked_as_having_no_work() -> None:
    """Both halves matter, and they are different questions.

    A reconnecting client asks this list whether its session still exists, so
    omitting empty ones would make it mint another. But a page refresh creates a
    session before the user has typed a word, so showing them all filled the
    sidebar with identical "New project" rows — has_work is what the display
    filters on.
    """

    async def run() -> None:
        gateway = AgentGateway()
        empty = (await gateway.handle(GatewayCommand(
            id="c1", method="session.create", params={}))).result["session_id"]
        used = (await gateway.handle(GatewayCommand(
            id="c2", method="session.create", params={}))).result["session_id"]
        await gateway.handle(GatewayCommand(id="t", method="task.submit", params={
            "session_id": used, "content": "Fit the model"}))

        listed = await gateway.handle(GatewayCommand(id="l", method="session.list", params={}))
        by_id = {item["session_id"]: item for item in listed.result["sessions"]}
        # Both exist…
        assert set(by_id) == {empty, used}
        # …but only one is a project worth showing.
        assert by_id[empty]["has_work"] is False
        assert by_id[used]["has_work"] is True

        # And it survives a restart, where task_ids do not come back.
        restarted = AgentGateway()
        await restarted._restore_sessions()  # noqa: SLF001
        reopened = await restarted.handle(GatewayCommand(id="l2", method="session.list", params={}))
        restored = {item["session_id"]: item for item in reopened.result["sessions"]}
        assert restored[used]["has_work"] is True and restored[used]["task_ids"] == []
        # The empty one left no manifest, so there is nothing to restore.
        assert empty not in restored

    asyncio.run(run())


def test_a_follow_up_stays_in_the_same_state_scope() -> None:
    """Otherwise "make it subtract instead" has no "it".

    ctx.id is the conversation, and memory is keyed by it. A client that omits
    conversation_id gets a fresh one per message — so the agent answering the
    second question cannot see the first. That is what the Chat view did.
    """

    async def run() -> None:
        gateway = AgentGateway()
        created = await gateway.handle(GatewayCommand(id="c", method="session.create", params={}))
        session_id = created.result["session_id"]

        first = await gateway.handle(GatewayCommand(id="t1", method="task.submit", params={
            "session_id": session_id, "view": "chat", "content": "write an add function"}))
        conversation = first.result["conversation_id"]

        second = await gateway.handle(GatewayCommand(id="t2", method="task.submit", params={
            "session_id": session_id, "view": "chat", "content": "make it subtract instead",
            "conversation_id": conversation}))
        assert second.result["conversation_id"] == conversation

        listed = await gateway.handle(GatewayCommand(
            id="l", method="conversation.list", params={"session_id": session_id, "view": "chat"}))
        assert len(listed.result["conversations"]) == 1, "one thread, not one per message"
        assert listed.result["conversations"][0]["task_count"] == 2

        # Both turns are in one transcript, so a reload shows the exchange.
        events = await gateway.handle(GatewayCommand(
            id="e", method="conversation.events",
            params={"session_id": session_id, "conversation_id": conversation}))
        assert [item["payload"]["content"] for item in events.result["events"]] == \
            ["write an add function", "make it subtract instead"]

    asyncio.run(run())
