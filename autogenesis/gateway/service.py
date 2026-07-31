"""Interactive service facade over the existing Autogenesis runtime."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from argparse import Namespace

from dotenv import load_dotenv
from lxml import etree, html as lxml_html
from autogenesis.agent import agent_manager
from autogenesis.benchmark import benchmark_manager
from autogenesis.canvas import canvas_manager
from autogenesis.conversation import Conversation, conversation_manager, title_from
from autogenesis.canvas.types import FlowGraph
from autogenesis.command import command_manager
from autogenesis.command.types import CommandContext
from autogenesis.config import config
from autogenesis.connector import connector_manager
from autogenesis.data import data_manager
from autogenesis.environment import environment_manager
from autogenesis.extension import extension_manager
from autogenesis.ide import ide_manager
from autogenesis.science import science_manager
from autogenesis.kernel import kernel_manager
from autogenesis.gateway.protocol import (
    PROTOCOL_VERSION,
    GatewayCommand,
    GatewayEvent,
    GatewayResponse,
    error_response,
)
from autogenesis.hook import hook_manager
from autogenesis.paths import P, path_manager
from autogenesis.session import project as session_project
from autogenesis.logger import logger
from autogenesis.memory import memory_manager
from autogenesis.knowledge import knowledge_manager
from autogenesis.model import model_manager
from autogenesis.model.types import ModelConfig
from autogenesis.plugins import plugin_manager
from autogenesis.process import process_manager
from autogenesis.prompt import prompt_manager
from autogenesis.session.types import SessionContext
from autogenesis.session.project import bind_session_roots
from autogenesis.sandbox.project import ProjectSandbox
from autogenesis.skill import skill_manager
from autogenesis.task import TaskCategory, TaskPriority, TaskRecord, task_manager
from autogenesis.trace import trace_manager
from autogenesis.trajectory import trajectory_manager
from autogenesis.utils import make_id
from autogenesis.version import version_manager
from autogenesis.tool import tool_manager
from autogenesis.workflow import workflow_manager
from autogenesis.deploy import deployment_manager
from autogenesis.environment.stream import environment_stream


@dataclass
class GatewaySession:
    context: SessionContext
    created_at: str
    sandbox: ProjectSandbox
    # The connection's owner (user) — the top level of the output tree:
    # output/<owner>/sessions/<id>/ (runtime) + output/<owner>/state/ (durable
    # flows/files/settings). Defaults to "local" for the single-user case.
    owner: str = "local"
    #: When work last happened here. Orders the project list — created_at would
    #: bury a project someone has lived in all week under one opened once.
    updated_at: str = ""
    #: Whether anything has actually happened here. A page refresh mints a new
    #: session before the user has typed a word, so listing every session in
    #: memory filled the project list with identical empty rows. The manifest is
    #: the same marker on disk: written on the first submission, which is also
    #: what makes a project restorable.
    has_work: bool = False
    task_ids: list[str] = field(default_factory=list)
    capabilities: Dict[str, list[str]] = field(default_factory=dict)
    uploads: Dict[str, "GatewayUpload"] = field(default_factory=dict)


@dataclass
class GatewayUpload:
    id: str
    name: str
    path: str
    size: int
    mime_type: str = "application/octet-stream"
    received: int = 0
    completed: bool = False

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "mime_type": self.mime_type,
            "completed": self.completed,
        }


class AgentGateway:
    """Owns interactive sessions and maps protocol commands to backend operations."""

    def __init__(
        self,
        *,
        event_history_size: int = 10_000,
        workspace_source: Optional[str | Path] = None,
    ) -> None:
        self._sessions: Dict[str, GatewaySession] = {}
        self._subscribers: set[asyncio.Queue[GatewayEvent]] = set()
        # Playground chats stream in background tasks (the WS command loop is
        # sequential, so a long stream must never run inside a handler).
        self._chat_tasks: Dict[str, asyncio.Task] = {}
        self._events: Dict[str, Deque[GatewayEvent]] = defaultdict(
            lambda: deque(maxlen=event_history_size)
        )
        self._sequence: Dict[str, int] = defaultdict(int)
        self._active_agent_tasks: Dict[str, asyncio.Task] = {}
        # Which session started which run. A run executes under its own context
        # — that is what keeps its memory and budget out of the conversation —
        # so its events do not carry the watching session's id and have to be
        # routed back by hand.
        self._run_sessions: Dict[str, str] = {}
        # Which conversation each running task belongs to, so the traces coming
        # out of it can be attributed. Cleared when the task ends.
        self._run_conversations: Dict[str, str] = {}
        # Session whose roots the shared runtime is currently bound to (see
        # _bind_runtime_to_session); None until the first task runs.
        self._bound_session_id: Optional[str] = None
        # Latest raw VNC websockify target (ws://<ephemeral-host-port>/...) as
        # reported by the browser environment. The gateway relays it over the
        # fixed /env/vnc route so a remote user only forwards the UI port — the
        # ephemeral port stays server-internal. See transport.py:/env/vnc.
        self._latest_vnc_target: Optional[str] = None
        self._initialized = False
        self._stopping = False
        self._workspace_source = (
            Path(workspace_source).expanduser().resolve() if workspace_source else None
        )

    _MAX_UPLOAD_SIZE = 100 * 1024 * 1024
    _MAX_UPLOAD_CHUNK_SIZE = 1024 * 1024
    _MAX_WORKSPACE_FILE_SIZE = 2 * 1024 * 1024
    # Media is returned base64 (≈33% larger on the wire), so keep the cap modest.
    _MAX_WORKSPACE_MEDIA_SIZE = 25 * 1024 * 1024
    _MEDIA_MIME_PREFIXES = ("image/", "audio/", "video/")
    _MEDIA_MIME_TYPES = frozenset({"application/pdf"})
    _MAX_WORKSPACE_ENTRIES = 500

    async def start(self, config_path: str, *, stdio: bool = False) -> None:
        """Initialize the configured runtime once for all Gateway sessions."""
        if self._initialized:
            return

        load_dotenv()
        config.initialize(config_path=config_path, args=Namespace(cfg_options=None), verbose=False)
        extension_manager.set_base_dir(config.extension_root)
        # No session exists yet, so do not open a tag-level log file — the file sink
        # is attached to the session's own log root by _bind_runtime_to_session.
        logger.initialize(config=config, console_stream=sys.stderr if stdio else None, file_logging=False)

        await version_manager.initialize()
        await trace_manager.initialize()
        await trace_manager.start()
        trace_manager.subscribe(self._on_trace_event)
        environment_stream.subscribe(self._on_environment_view)
        await trajectory_manager.initialize()
        await hook_manager.initialize()
        await model_manager.initialize()
        await prompt_manager.initialize(prompt_names=getattr(config, "prompt_names", None))
        await memory_manager.initialize(memory_names=getattr(config, "memory_names", None))
        await tool_manager.initialize(tool_names=getattr(config, "tool_names", None))
        await skill_manager.initialize(skill_names=getattr(config, "skill_names", None))
        await connector_manager.initialize(connector_names=getattr(config, "connector_names", None))
        await plugin_manager.initialize(plugin_names=getattr(config, "plugin_names", None))
        await process_manager.initialize(process_names=getattr(config, "process_names", None))
        await data_manager.initialize()
        await knowledge_manager.initialize()
        # Init ONLY the dataset-free evaluators by default — building every
        # benchmark would download datasets (slow/noisy). ``exact_match`` needs
        # no data; add more via config.benchmark_names when a run wants them.
        await benchmark_manager.initialize(
            benchmark_names=getattr(config, "benchmark_names", None) or ["exact_match"]
        )
        env_names = getattr(config, "env_names", None)
        if env_names:
            await environment_manager.initialize(env_names=env_names)
            # A failed environment is silently absent from the registry; surface
            # it loudly so an empty capability list is never a mystery.
            registered_envs = await environment_manager.list()
            missing_envs = [name for name in env_names if name not in registered_envs]
            if missing_envs:
                logger.error(
                    f"| ❌ {len(missing_envs)} configured environment(s) failed to initialize and are "
                    f"unavailable this run: {', '.join(missing_envs)} — see the errors above; "
                    f"stale sandboxes are reaped at boot, so a restart usually recovers."
                )
        await agent_manager.initialize(agent_names=getattr(config, "agent_names", None))
        await workflow_manager.initialize(workflow_names=getattr(config, "workflow_names", None))
        # Deploy registry is project-global (output/.runtime/deploy), so init it
        # once here — before any session binds — and reconcile sites still serving.
        await deployment_manager.initialize()
        await canvas_manager.initialize()
        await command_manager.initialize()
        await extension_manager.initialize()
        extension_manager.subscribe(self._on_extension_change)

        task_dir = os.path.join(config.log_root, "gateway", "tasks")
        await task_manager.initialize(log_root=task_dir, handler=self._run_task)
        await task_manager.start(num_workers=1)
        # Bring back sessions that already have work on disk, so a restart does
        # not strand their workspaces with no way to reopen them.
        await self._restore_sessions()
        self._initialized = True
        await self._publish("gateway.ready", {"protocol_version": PROTOCOL_VERSION})

    async def stop(self) -> None:
        if not self._initialized or self._stopping:
            return
        self._stopping = True
        for task in tuple(self._active_agent_tasks.values()):
            task.cancel()
        await asyncio.gather(*self._active_agent_tasks.values(), return_exceptions=True)
        self._active_agent_tasks.clear()
        for task in tuple(self._chat_tasks.values()):
            task.cancel()
        await asyncio.gather(*self._chat_tasks.values(), return_exceptions=True)
        self._chat_tasks.clear()
        await task_manager.stop()
        await ide_manager.stop_all()
        await science_manager.stop_all()
        extension_manager.unsubscribe(self._on_extension_change)
        trace_manager.unsubscribe(self._on_trace_event)
        environment_stream.unsubscribe(self._on_environment_view)
        await trace_manager.stop()
        await canvas_manager.cleanup()
        await workflow_manager.cleanup()
        await agent_manager.cleanup()
        await command_manager.cleanup()
        self._initialized = False

    async def handle(self, command: GatewayCommand) -> GatewayResponse:
        if command.protocol_version != PROTOCOL_VERSION:
            return error_response(
                command.id,
                "unsupported_protocol",
                f"Expected protocol version {PROTOCOL_VERSION}",
            )
        try:
            handler = getattr(self, f"_command_{command.method.replace('.', '_')}", None)
            if handler is None:
                return error_response(command.id, "unknown_method", f"Unknown method: {command.method}")
            result = await handler(command.params)
            return GatewayResponse(id=command.id, ok=True, result=result or {})
        except ValueError as exc:
            return error_response(command.id, "invalid_request", str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"| ❌ Gateway command {command.method} failed: {exc}", exc_info=True)
            return error_response(command.id, "internal_error", str(exc))

    async def subscribe(self) -> asyncio.Queue[GatewayEvent]:
        queue: asyncio.Queue[GatewayEvent] = asyncio.Queue(maxsize=2_000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[GatewayEvent]) -> None:
        self._subscribers.discard(queue)

    async def _command_hello(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "transports": ["stdio", "websocket"],
            "sessions": len(self._sessions),
        }

    async def _command_session_create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = params.get("session_id") or make_id()
        if session_id in self._sessions:
            raise ValueError(f"Session already exists: {session_id}")
        if params.get("project_root") is not None:
            raise ValueError("project_root is server-managed; create a session without this parameter")
        # Output tree: output/<owner>/sessions/<session_id>/{workspace,log,runs}
        # for runtime; output/<owner>/state/ for the owner's durable library
        # (flows/files/settings). owner = the connection's user (default "local").
        owner = self._owner_for(params)
        requested_workspace = params.get("workspace")
        requested_source = Path(requested_workspace).expanduser().resolve() if requested_workspace else None
        if requested_source and (
            self._workspace_source is None or requested_source != self._workspace_source
        ):
            raise ValueError("workspace must match the server-controlled workspace source")
        source_workspace = str(self._workspace_source) if self._workspace_source else None
        # Clients open a session as soon as they connect; most never run anything.
        # The sandbox is only described here — it is created, and the manifest
        # written, on first real use, so idle sessions leave nothing behind.
        session = self._build_session(
            session_id=session_id, owner=owner,
            name=params.get("name") or "interactive",
            source_workspace=source_workspace,
            created_at=datetime.now(timezone.utc).isoformat(),
            capabilities=await self._available_capabilities(),
        )
        sandbox, context = session.sandbox, session.context
        self._sync_session_capabilities(session)
        self._sessions[session_id] = session
        payload = {"workspace": str(sandbox.workspace_root), "project_root": str(sandbox.project_root), "extension_root": str(sandbox.extension_root), "name": context.name, "source_workspace": source_workspace}
        await self._publish("session.created", payload, session_id=session_id)
        return {"session_id": session_id, **payload, "sandbox": sandbox.describe(), "mounts": sandbox.mounts()}

    #: Session identity is written by the shared session layer, so a session
    #: created here and one created by a local run are equally discoverable.
    SESSION_MANIFEST = session_project.SESSION_MANIFEST

    def _write_session_manifest(self, session: "GatewaySession") -> None:
        """Record identity + roots so this session can be reopened after a restart."""
        session.updated_at = datetime.now(timezone.utc).isoformat()
        session.has_work = True
        session_project.write_session_manifest(
            session.sandbox,
            session_id=session.context.id,
            owner=session.owner,
            name=session.context.name,
            created_at=session.created_at,
            source_workspace=session.context.extra.get("source_workspace"),
        )

    def _seed_sequence(self, conversation_id: str, owner: str, session_id: str) -> None:
        """Continue a conversation's numbering after a restart.

        The counter lives in memory and dies with the process, so a restored
        conversation would restart at 1 and its new events would collide with
        the replayed ones. Seeded from the transcript the first time the
        conversation is touched in this process.
        """
        if conversation_id in self._sequence:
            return
        highest = 0
        for event in conversation_manager.events(owner, session_id, conversation_id):
            highest = max(highest, int(event.get("seq_no") or 0))
        self._sequence[conversation_id] = highest

    def _append_event_log(self, event: GatewayEvent) -> None:
        """Record one event in its conversation's transcript.

        Only conversational events are kept: a project opening or its
        capabilities settling belongs to no line of dialogue, and replaying it
        into one would put it in a transcript nobody wrote. The file is the
        source of truth — the in-memory buffer only serves live clients — so a
        reopened conversation reads back the same way after a restart.
        """
        if not event.conversation_id or not event.session_id:
            return
        session = self._sessions.get(event.session_id)
        if session is None:
            return
        conversation_manager.append(session.owner, event.session_id, event.conversation_id,
                                    event.model_dump(mode="json"))

    def _adopt_legacy_transcript(self, session_id: str) -> None:
        """Fold a pre-conversation transcript into one, so history is not lost.

        Projects written before conversations existed kept a single
        ``events.jsonl``. Left alone it would simply stop being read — the
        transcript would still be on disk with nothing able to open it. It
        becomes the project's first conversation instead, marked as migrated so
        the rewrite is visible rather than silent.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return
        legacy = path_manager.get(P.SESSION, owner=session.owner, session_id=session_id) / "events.jsonl"
        if not legacy.is_file():
            return
        if conversation_manager.list(session.owner, session_id):
            return  # already migrated, or the project moved on without it
        conversation = Conversation(session_id=session_id, view="chat",
                                    title="Earlier conversation", migrated=True)
        conversation_manager.save(session.owner, conversation)
        target = path_manager.get(P.CONVERSATION_EVENTS, owner=session.owner,
                                  session_id=session_id, conversation_id=conversation.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
        legacy.rename(legacy.with_suffix(".jsonl.migrated"))
        logger.info(f"| ♻️ Adopted the pre-conversation transcript of {session_id} as {conversation.id}")

    async def _restore_sessions(self) -> None:
        """Rebuild sessions that have a manifest on disk, so their workspaces stay reachable.

        Without this the session registry is purely in-memory: a restart leaves
        every workspace on disk with no way to open it from the UI. The
        conversation comes back too, replayed from the session's event log.
        """
        base = self._output_base()
        if not base.is_dir():
            return
        restored = 0
        for manifest in sorted(base.glob(f"*/sessions/*/{self.SESSION_MANIFEST}")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                session_id = str(data["session_id"])
                if session_id in self._sessions:
                    continue
                self._sessions[session_id] = self._build_session(
                    session_id=session_id,
                    owner=str(data.get("owner") or "local"),
                    name=str(data.get("name") or "interactive"),
                    source_workspace=data.get("source_workspace"),
                    created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    # Manifests written before this field existed fall back to
                    # created_at, which orders them plausibly rather than first.
                    updated_at=str(data.get("updated_at") or data.get("created_at") or ""),
                    capabilities=await self._available_capabilities(),
                )
                # It has a manifest, so it earned one: work happened here before
                # the restart even though task_ids are not carried across.
                self._sessions[session_id].has_work = True
                self._adopt_legacy_transcript(session_id)
                restored += 1
            except Exception as exc:  # noqa: BLE001 — one bad manifest must not block startup
                logger.warning(f"| ⚠️ Skipping unreadable session manifest {manifest}: {exc}")
        if restored:
            logger.info(f"| ♻️ Restored {restored} session(s) from disk")

    def _build_session(
        self, *, session_id: str, owner: str, name: str,
        source_workspace: Optional[str], created_at: str, capabilities: Dict[str, list],
        updated_at: str = "",
    ) -> "GatewaySession":
        """Construct a session over ``output/<owner>/sessions/<id>``.

        Shared by session.create and restore so both produce the same object; the
        sandbox is described but not materialized, which keeps an untouched
        session free of directories and lets a restored one reuse what is there.
        """
        project_root = path_manager.get(P.SESSION, owner=owner, session_id=session_id)
        sandbox = ProjectSandbox.create(
            project_root, shared_extension_root=Path(config.extension_root), materialize=False,
        )
        context = SessionContext(
            id=session_id,
            name=name,
            workspace_root=str(sandbox.workspace_root),
            extra={
                "workspace": str(sandbox.workspace_root),
                **sandbox.describe(),
                "gateway_session": True,
                "sandbox_mounts": sandbox.mounts(),
                "source_workspace": source_workspace,
                # The project this context belongs to. ctx.id follows the
                # conversation (memory, budgets, todos), so anything that costs
                # a container has to be keyed off this instead — otherwise a
                # second line of dialogue silently starts a second container.
                "project_id": session_id,
            },
        )
        return GatewaySession(
            context=context, created_at=created_at, sandbox=sandbox,
            owner=owner, capabilities=capabilities, updated_at=updated_at or created_at,
        )

    async def _command_session_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        # Most recently worked in first: the list is how someone gets back to
        # what they were doing, so the thing they were doing belongs at the top.
        # Every session, including ones nothing has happened in yet: this answers
        # "does this session exist", which is what a reconnecting client asks.
        # Whether a session is worth SHOWING is a display question, and travels
        # as has_work rather than as an omission from the list.
        ordered = sorted(self._sessions.items(),
                         key=lambda item: item[1].updated_at or item[1].created_at, reverse=True)
        return {
            "sessions": [
                {
                    "session_id": session_id,
                    "name": session.context.name,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at or session.created_at,
                    # False until the first submission. A page refresh mints a
                    # session before the user has typed anything, so a sidebar
                    # that listed them all filled up with identical empty rows.
                    "has_work": session.has_work,
                    "workspace": str(session.sandbox.workspace_root),
                    "source_workspace": session.context.extra.get("source_workspace"),
                    "project_root": str(session.sandbox.project_root),
                    "extension_root": str(session.sandbox.extension_root),
                    "task_ids": session.task_ids,
                }
                for session_id, session in ordered
            ]
        }

    async def _command_extension_stage_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        sandbox = self._sessions[session_id].sandbox
        try:
            validation = sandbox.validate()
            validation["valid"] = True
        except ValueError as exc:
            validation = {"valid": False, "error": str(exc), "components": sandbox.staged_components()}
        return {"sandbox": sandbox.describe(), "mounts": sandbox.mounts(), "staging": validation}

    async def _command_extension_promote(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        sandbox = self._sessions[session_id].sandbox
        before = extension_manager.read_manifest()
        report = sandbox.promote(
            overwrite=bool(params.get("overwrite", False)),
            relative_paths=params.get("relative_paths"),
        )
        registered: list[Dict[str, str]] = []
        try:
            for component in report["promoted"]:
                module = component["module"]
                config_data = {"enable_evolving": True} if module != "prompt" else None
                name = await extension_manager.add_component(
                    module, component["destination"], config=config_data,
                    run_smoke=params.get("run_smoke"),
                )
                registered.append({"module": module, "name": name, "path": component["destination"]})
        except Exception:
            for item in reversed(registered):
                try:
                    await extension_manager.unload(item["module"], item["name"])
                except Exception as rollback_error:  # continue restoring the batch
                    logger.error(
                        f"| ❌ Failed to unload partial promotion "
                        f"{item['module']}:{item['name']}: {rollback_error}",
                        exc_info=True,
                    )
            try:
                sandbox.rollback_promotion(report)
            finally:
                # add_component may have unloaded the failing live component before
                # raising. Restore the exact pre-transaction active set even when
                # filesystem cleanup itself reports an error.
                await extension_manager.restore_manifest(before)
            raise
        sandbox.mark_promotion(report, "committed")
        payload = {**report, "registered": registered}
        await self._publish("extension.promoted", payload, session_id=session_id)
        return payload

    async def _command_session_rename(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        name = str(params.get("name") or "").strip()
        if not name:
            raise ValueError("Session name is required")
        if len(name) > 100:
            raise ValueError("Session name must be at most 100 characters")
        session = self._sessions[session_id]
        session.context.name = name
        await self._publish("session.renamed", {"name": name}, session_id=session_id)
        return {"session_id": session_id, "name": name}

    # Task lifecycle event types, used to detect orphaned (interrupted) tasks.
    _TASK_START_EVENTS = ("task.started",)
    _TASK_TERMINAL_EVENTS = ("task.completed", "task.failed", "task.cancelled")

    async def _reconcile_orphan_tasks(self, session_id: str) -> None:
        """Close out tasks that began but never reached a terminal event and are
        no longer running — e.g. the runtime was interrupted/restarted while a
        task was in flight, so `task.completed` was never emitted and the client
        activity would otherwise hang on "Working" forever. Emitting a synthetic
        `task.cancelled` lets the replaying client resolve the activity. A task
        still in `_active_agent_tasks` is genuinely running and left untouched;
        if a just-started task is closed here by a race, its real terminal event
        (published when it finishes) supersedes this one on the client."""
        started: set[str] = set()
        terminal: set[str] = set()
        for event in self._events[session_id]:
            if not event.task_id:
                continue
            if event.type in self._TASK_START_EVENTS:
                started.add(event.task_id)
            elif event.type in self._TASK_TERMINAL_EVENTS:
                terminal.add(event.task_id)
        for task_id in started - terminal:
            if task_id in self._active_agent_tasks:
                continue
            await self._publish(
                "task.cancelled",
                {"reason": "interrupted", "detail": "Task did not finish — the runtime was interrupted or restarted."},
                session_id=session_id,
                task_id=task_id,
            )

    # ------------------------------------------------------------------
    # Conversations — the lines of dialogue inside a project. A project holds
    # several (one per investigation, per view); each owns its transcript and,
    # through ctx.id, the agent memory and budgets spent in it.
    # ------------------------------------------------------------------

    async def _command_conversation_create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        conversation = conversation_manager.create(
            session.owner, session.context.id,
            view=str(params.get("view") or "chat"), title=str(params.get("title") or ""))
        return {"conversation": conversation.summary()}

    async def _command_conversation_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        view = params.get("view")
        items = conversation_manager.list(session.owner, session.context.id,
                                          view=str(view) if view else None)
        return {"conversations": [item.summary() for item in items]}

    async def _command_conversation_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """One conversation's transcript, for opening or reconnecting to it.

        Read from the transcript on disk rather than the in-memory buffer: the
        buffer is bounded and dies with the process, so this is what lets a
        conversation reopen intact after a restart.
        """
        session = self._sessions[self._require_session_id(params)]
        conversation_id = str(params.get("conversation_id") or "")
        if not conversation_id:
            raise ValueError("conversation_id is required")
        after_seq = int(params.get("after_seq", 0))
        events = [event for event in conversation_manager.events(session.owner, session.context.id, conversation_id)
                  if int(event.get("seq_no") or 0) > after_seq]
        return {"events": events}

    async def _command_conversation_rename(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        conversation = conversation_manager.rename(
            session.owner, session.context.id,
            str(params.get("conversation_id") or ""), str(params.get("title") or "").strip())
        if conversation is None:
            raise ValueError("Unknown conversation")
        return {"conversation": conversation.summary()}

    async def _command_conversation_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        conversation_id = str(params.get("conversation_id") or "")
        deleted = conversation_manager.delete(session.owner, session.context.id, conversation_id)
        return {"conversation_id": conversation_id, "deleted": deleted}

    async def _command_session_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        after_seq = int(params.get("after_seq", 0))
        # Resolve any interrupted-but-unfinished tasks before replaying, so a
        # reconnecting client never rebuilds a permanently-"Working" activity.
        await self._reconcile_orphan_tasks(session_id)
        return {
            "events": [event.model_dump(mode="json") for event in self._events[session_id] if event.seq_no > after_seq]
        }

    async def _command_task_submit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        content = str(params.get("content") or "").strip()
        if not content:
            raise ValueError("Task content is required")
        files = [str(item) for item in params.get("files", [])]
        workspace = Path(str(self._sessions[session_id].sandbox.workspace_root)).resolve()
        for path in files:
            try:
                Path(path).expanduser().resolve().relative_to(workspace)
            except ValueError as exc:
                raise ValueError("Task files must be located inside the session workspace") from exc
        session = self._sessions[session_id]
        # Bind before submitting so the queue persists this task under the session.
        self._bind_runtime_to_session(session)
        conversation = self._resolve_conversation(session, params)
        task_id = await task_manager.submit(
            content=content,
            category=TaskCategory.USER,
            priority=TaskPriority.HIGH,
            files=files,
            metadata={"source": "gateway", "conversation_id": conversation.id},
            session_id=session_id,
        )
        # A project is named by the first thing asked of it, the way a
        # conversation is. Sessions were called "web" or "Web session 10:23" —
        # machine placeholders the frontend invented, identical to each other
        # and describing nothing, which made a list of past projects useless.
        if not session.task_ids:
            session.context.name = title_from(content)
        session.task_ids.append(task_id)
        # Rewrite the manifest: it carries the new title, and its updated_at is
        # what orders the project list by what was touched last.
        self._write_session_manifest(session)
        # The conversation names itself from its opening message, and remembers
        # which submissions were made in it.
        conversation_manager.note_task(session.owner, session_id, conversation.id, task_id, content)
        await self._publish("task.submitted", {"content": content, "files": files},
                            session_id=session_id, conversation_id=conversation.id, task_id=task_id)
        return {"task_id": task_id, "conversation_id": conversation.id}

    def _resolve_conversation(self, session: "GatewaySession", params: Dict[str, Any]):
        """The conversation this request belongs to, opening one if needed.

        Clients name it; a client that does not gets a fresh one rather than an
        implicit shared default, so two views never end up writing into each
        other's transcript.
        """
        conversation_id = str(params.get("conversation_id") or "")
        view = str(params.get("view") or "chat")
        if conversation_id:
            existing = conversation_manager.get(session.owner, session.context.id, conversation_id)
            if existing is not None:
                self._seed_sequence(existing.id, session.owner, session.context.id)
                return existing
        conversation = conversation_manager.create(session.owner, session.context.id, view=view)
        self._seed_sequence(conversation.id, session.owner, session.context.id)
        return conversation

    async def _command_file_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        return {"files": [upload.public() for upload in session.uploads.values() if upload.completed]}

    def _workspace_path(self, session: GatewaySession, value: Any) -> tuple[Path, str]:
        """Resolve a client relative path without permitting cross-session access."""
        raw = str(value or "").replace("\\", "/")
        if raw.startswith("/"):
            raise ValueError("Workspace paths must be relative")
        relative = raw.strip("/")
        parts = Path(relative).parts
        if ".." in parts:
            raise ValueError("Workspace paths must be relative and may not contain '..'")
        root = session.sandbox.workspace_root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("Workspace path escapes the current session") from exc
        return candidate, relative

    async def _command_workspace_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List one workspace directory; clients expand the tree lazily."""
        session = self._sessions[self._require_session_id(params)]
        directory, relative = self._workspace_path(session, params.get("path"))
        if not directory.exists() and not relative:
            # Session opened but nothing has run yet, so its workspace does not exist
            # on disk. Report it as empty rather than an error.
            return {"path": relative, "entries": [], "truncated": False}
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Workspace directory was not found: {relative or '.'}")
        show_hidden = bool(params.get("show_hidden", False))
        entries = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if not show_hidden and child.name.startswith("."):
                continue
            # Do not expose symlinks that resolve beyond this session workspace.
            try:
                child.resolve().relative_to(session.sandbox.workspace_root.resolve())
            except ValueError:
                continue
            stat = child.stat()
            child_relative = child.relative_to(session.sandbox.workspace_root).as_posix()
            entries.append({
                "name": child.name,
                "path": child_relative,
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if child.is_file() else None,
                "modified_at": stat.st_mtime,
            })
            if len(entries) >= self._MAX_WORKSPACE_ENTRIES:
                break
        return {
            "path": relative,
            "entries": entries,
            "truncated": len(entries) >= self._MAX_WORKSPACE_ENTRIES,
        }

    async def _command_workspace_file_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a bounded workspace file: UTF-8 text, or base64 for media.

        Images, audio, video and PDFs are returned base64-encoded (``encoding``
        says which) so the client can render them directly from a data URL,
        rather than being rejected as "binary".
        """
        session = self._sessions[self._require_session_id(params)]
        path, relative = self._workspace_path(session, params.get("path"))
        if not relative or not path.exists() or not path.is_file():
            raise ValueError(f"Workspace file was not found: {relative or '.'}")
        mime_type = mimetypes.guess_type(path.name)[0] or ""
        is_media = mime_type.startswith(self._MEDIA_MIME_PREFIXES) or mime_type in self._MEDIA_MIME_TYPES

        size = path.stat().st_size
        limit = self._MAX_WORKSPACE_MEDIA_SIZE if is_media else self._MAX_WORKSPACE_FILE_SIZE
        if size > limit:
            raise ValueError(
                f"Workspace file is larger than the {limit // (1024 * 1024)} MB preview limit"
            )
        raw = path.read_bytes()

        if is_media:
            content = base64.b64encode(raw).decode("ascii")
            encoding = "base64"
            language = "plaintext"
        else:
            if b"\x00" in raw[:8192]:
                raise ValueError("Binary files cannot be opened in the text preview")
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("File is not valid UTF-8 text") from exc
            encoding = "utf-8"
            mime_type = mime_type or "text/plain"
            language = self._workspace_language(path.suffix.lower())

        return {
            "path": relative,
            "name": path.name,
            "content": content,
            "encoding": encoding,
            "size": size,
            "modified_at": path.stat().st_mtime,
            "etag": hashlib.sha256(raw).hexdigest(),
            "mime_type": mime_type,
            "language": language,
        }

    @staticmethod
    def _workspace_language(suffix: str) -> str:
        return {
            ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".html": "html", ".htm": "html",
            ".css": "css", ".scss": "scss", ".json": "json", ".yaml": "yaml",
            ".yml": "yaml", ".md": "markdown", ".mdx": "markdown", ".sh": "shell",
            ".bash": "shell", ".zsh": "shell", ".toml": "ini", ".ini": "ini",
            ".xml": "xml", ".sql": "sql", ".dockerfile": "dockerfile",
        }.get(suffix, "plaintext")

    async def _command_file_upload_begin(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        name = self._safe_upload_name(params.get("name"))
        size = params.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValueError("size must be a non-negative integer")
        if size > self._MAX_UPLOAD_SIZE:
            raise ValueError("File exceeds the 2 GB upload limit")
        mime_type = str(params.get("mime_type") or "application/octet-stream")[:255]
        upload_id = make_id()
        # Uploads are DURABLE per-owner assets: output/<owner>/state/files. They
        # outlive the session and are staged into a run's workspace on demand
        # (session.project.stage_input_files), not written into the sandbox here.
        upload_dir = path_manager.get(P.OWNER_FILES, owner=session.owner)
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{upload_id}_{name}"
        path.touch(exist_ok=False)
        upload = GatewayUpload(id=upload_id, name=name, path=str(path), size=size, mime_type=mime_type)
        session.uploads[upload_id] = upload
        return {"file": upload.public()}

    async def _command_file_upload_chunk(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        upload = self._require_upload(session, params)
        if upload.completed:
            raise ValueError("Upload is already complete")
        encoded = params.get("data")
        if not isinstance(encoded, str):
            raise ValueError("data must be base64 text")
        try:
            chunk = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("data must be valid base64 text") from exc
        if len(chunk) > self._MAX_UPLOAD_CHUNK_SIZE:
            raise ValueError("Upload chunk exceeds the 1 MB limit")
        if upload.received + len(chunk) > upload.size:
            raise ValueError("Upload contains more data than the declared file size")
        with Path(upload.path).open("ab") as file:
            file.write(chunk)
        upload.received += len(chunk)
        return {"file_id": upload.id, "received": upload.received, "size": upload.size}

    async def _command_file_upload_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        upload = self._require_upload(session, params)
        if upload.received != upload.size:
            raise ValueError(f"Upload is incomplete ({upload.received} of {upload.size} bytes received)")
        upload.completed = True
        await self._publish("file.uploaded", {"file": upload.public()}, session_id=session.context.id)
        return {"file": upload.public()}

    async def _command_file_remove(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        upload = self._require_upload(session, params)
        Path(upload.path).unlink(missing_ok=True)
        session.uploads.pop(upload.id, None)
        return {"file_id": upload.id, "removed": True}

    @staticmethod
    def _safe_upload_name(value: Any) -> str:
        name = Path(str(value or "")).name
        name = re.sub(r"[^A-Za-z0-9._()\- ]", "_", name).strip(" .")
        if not name:
            raise ValueError("A valid file name is required")
        return name[:180]

    @staticmethod
    def _require_upload(session: GatewaySession, params: Dict[str, Any]) -> GatewayUpload:
        upload_id = str(params.get("file_id") or "")
        upload = session.uploads.get(upload_id)
        if upload is None:
            raise ValueError("Unknown uploaded file")
        return upload

    async def _command_task_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(params.get("task_id") or "")
        if not task_id:
            raise ValueError("task_id is required")
        active = self._active_agent_tasks.get(task_id)
        if active is not None:
            active.cancel()
            return {"task_id": task_id, "cancelled": True}
        cancelled = await task_manager.cancel(task_id)
        return {"task_id": task_id, "cancelled": cancelled}

    async def _command_capability_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """Capabilities enriched per item with ``{type, name, source, evolving}``:
        ``source`` is ``extension`` when the capability's file lives under the
        shared extension root, else ``default``; ``evolving`` reflects
        ``enable_evolving``. The interactive UI renders these as per-item tags."""
        import os
        from inspect import getfile

        ext_root = os.path.realpath(str(getattr(config, "extension_root", "") or "")) or None
        managers = {
            "skills": skill_manager, "tools": tool_manager, "agents": agent_manager,
            "connectors": connector_manager, "environments": environment_manager,
        }
        type_of = {"skills": "skill", "tools": "tool", "agents": "agent", "connectors": "connector",
                   "environments": "environment", "workflows": "workflow", "commands": "command",
                   "canvas": "canvas"}

        def source_of(info: Any) -> str:
            candidates = [getattr(info, a, None) for a in ("path", "skill_dir", "connector_dir", "source_path")]
            cls = getattr(info, "cls", None)
            if cls is not None:
                try:
                    candidates.append(getfile(cls))
                except (TypeError, OSError):
                    pass
            for p in candidates:
                if not p:
                    continue
                try:
                    rp = os.path.realpath(str(p))
                except (TypeError, ValueError):
                    continue
                if ext_root and (rp == ext_root or rp.startswith(ext_root + os.sep)):
                    return "extension"
            return "default"

        async def info_for(kind: str, name: str) -> Any:
            try:
                if kind == "workflows":
                    return workflow_manager.get(name)
                if kind == "commands":
                    return await command_manager.get(name)
                mgr = managers.get(kind)
                if mgr is not None and hasattr(mgr, "get_info"):
                    res = mgr.get_info(name)
                    return await res if asyncio.iscoroutine(res) else res
            except Exception:  # noqa: BLE001 — a broken lookup must not drop the list
                return None
            return None

        result: Dict[str, list] = {}
        for kind, names in (await self._available_capabilities()).items():
            items = []
            canvas_defaults = set(canvas_manager.list_default_names()) if kind == "canvas" else set()
            for name in names:
                if kind == "canvas":
                    # Shipped templates are `default`; user library flows `extension`.
                    src = "default" if name in canvas_defaults else "extension"
                    items.append({"type": "canvas", "name": name, "source": src, "evolving": False})
                    continue
                info = await info_for(kind, name)
                items.append({
                    "type": type_of.get(kind, kind),
                    "name": name,
                    "source": source_of(info) if info is not None else "default",
                    "evolving": bool(getattr(info, "enable_evolving", False)) if info is not None else False,
                })
            result[kind] = items
        return result

    async def _command_workflow_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch a registered workflow without blocking the interactive Gateway."""
        session_id = self._require_session_id(params)
        name = str(params.get("name") or "")
        if not name:
            raise ValueError("name is required")
        run_id = workflow_manager.start(
            name, input=params.get("input") or {}, ctx=self._sessions[session_id].context,
        )
        return {"run_id": run_id, "state": "created"}

    async def _command_workflow_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        run = workflow_manager.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown workflow run: {run_id}")
        return run.model_dump(mode="json")

    async def _command_workflow_pause(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        return {"run_id": run_id, "accepted": workflow_manager.pause(run_id)}

    async def _command_workflow_continue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        return {"run_id": run_id, "accepted": workflow_manager.continue_run(run_id)}

    async def _command_workflow_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        return {"run_id": run_id, "accepted": workflow_manager.cancel(run_id)}

    async def _command_workflow_restore(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        name, checkpoint = str(params.get("name") or ""), str(params.get("checkpoint") or "")
        if not name or not checkpoint:
            raise ValueError("name and checkpoint are required")
        run = await workflow_manager.resume(
            name, checkpoint, ctx=self._sessions[session_id].context,
        )
        return run.model_dump(mode="json")

    async def _command_capability_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        kind = str(params.get("kind") or "")
        name = str(params.get("name") or "")
        return await self._capability_detail(kind, name)

    # ------------------------------------------------------------------
    # Deploy — project-global registry of sites/services the agents deployed
    # ------------------------------------------------------------------

    async def _command_deploy_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """Return every deployed site (project-global; survives sessions/restarts)."""
        sites = await deployment_manager.list_sites()
        return {"sites": [site.model_dump(mode="json") for site in sites]}

    async def _command_port_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """Return the central port registry (framework host + env + deploy ports)."""
        from autogenesis.port import port_manager
        return {"ports": port_manager.list()}

    async def _command_deploy_redeploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Rebuild a stopped/detached site from its stored request (new URL likely)."""
        site_id = str(params.get("site_id") or "")
        if not site_id:
            raise ValueError("site_id is required")
        site = await deployment_manager.redeploy(site_id)
        await self._publish("deploy.changed", {"action": "redeploy", "site_id": site_id})
        return site.model_dump(mode="json")

    async def _command_deploy_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop a running site; its record stays for later redeploy."""
        site_id = str(params.get("site_id") or "")
        if not site_id:
            raise ValueError("site_id is required")
        site = await deployment_manager.stop_site(site_id)
        await self._publish("deploy.changed", {"action": "stop", "site_id": site_id})
        return site.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Canvas — visual workflow editor (JSON source → workflow HTML artifact)
    # ------------------------------------------------------------------

    async def _command_canvas_catalog(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """Return the palette (structural/io/agents/workflows) plus the capability
        rosters the agent capability picker mounts from."""
        specs = await canvas_manager.catalog()
        return {
            "nodes": [spec.model_dump(mode="json") for spec in specs],
            "mounts": await canvas_manager.mounts(),
        }

    # ------------------------------------------------------------------
    # Output tree helpers — output/<owner>/{sessions/<id>, state/{flows,files}}
    # ------------------------------------------------------------------

    @staticmethod
    def _output_base() -> Path:
        """The output/ root. Taken from the layout table rather than derived from
        config.project_root, which moves the moment a session binds."""
        return path_manager.get(P.OUTPUT)

    @staticmethod
    def _owner_for(params: Dict[str, Any]) -> str:
        """Resolve the connection's owner (user). Sanitized to a safe dir name;
        defaults to "local" for the single-user case (multi-user auth later)."""
        raw = str(params.get("user_id") or "local").strip()
        safe = "".join(char for char in raw if char.isalnum() or char in "-_")
        return safe or "local"

    @staticmethod
    def _owner_state_dir(owner: str) -> Path:
        """The owner's durable library root: flows/, files/, settings.json."""
        return path_manager.get(P.OWNER_STATE, owner=owner)

    def _owner_sessions_dir(self, owner: str) -> Path:
        """The owner's session records + runtime root."""
        return self._output_base() / owner / "sessions"

    def _canvas_flows_dir(self, session_id: str) -> Path:
        """Draft flows belong to the session that drew them.

        A finished flow is promoted to the shared library (``extension/canvas``)
        with ``canvas.library.export``, which is what makes it reusable from any
        session — so drafts do not also have to be global.
        """
        return path_manager.get(P.SESSION_FLOWS, owner=self._sessions[session_id].owner,
                                session_id=session_id)

    def _canvas_runs_dir(self, session_id: str) -> Path:
        """Where this session records which runs each of its flows produced."""
        return path_manager.get(P.SESSION_RUNS, owner=self._sessions[session_id].owner,
                                session_id=session_id)

    # ------------------------------------------------------------------
    # Chat sessions — persistent per-owner conversation records at
    #   output/<owner>/sessions/<session_id>/{meta.json, chat.jsonl, feedback.jsonl}
    # These are gateway-managed record files (written directly, independent of the
    # sandbox), so the sidebar can list/reopen past conversations.
    # ------------------------------------------------------------------

    def _session_record_dir(self, owner: str, session_id: str) -> Path:
        safe = "".join(char for char in session_id if char.isalnum() or char in "-_")
        if not safe or safe != session_id:
            raise ValueError(f"Invalid session id: {session_id!r}")
        return self._owner_sessions_dir(owner) / safe

    async def _command_chat_append(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Append one message to a conversation's transcript + update meta. The
        chat-record id is decoupled from the live WS session, so the playground
        can keep several conversations under one connection (sidebar switching)."""
        session_id = str(params.get("session_id") or "")
        if not session_id:
            raise ValueError("session_id is required")
        live = self._sessions.get(session_id)
        owner = live.owner if live else self._owner_for(params)
        role = str(params.get("role") or "")
        if role not in ("user", "assistant"):
            raise ValueError("role must be 'user' or 'assistant'")
        rec_dir = self._session_record_dir(owner, session_id)
        rec_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        entry: Dict[str, Any] = {"role": role, "content": params.get("content"), "ts": now}
        if params.get("tab"):
            entry["tab"] = params["tab"]
        with (rec_dir / "chat.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        meta_path = rec_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        except Exception:  # noqa: BLE001
            meta = {}
        meta.setdefault("session_id", session_id)
        meta.setdefault("created_at", now)
        if params.get("flow_id"):
            meta["flow_id"] = params["flow_id"]
        if not meta.get("title") and role == "user" and isinstance(entry["content"], str):
            meta["title"] = entry["content"].strip()[:60] or None
        meta["updated_at"] = now
        meta["message_count"] = int(meta.get("message_count", 0)) + 1
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    async def _command_chat_sessions_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Every persisted conversation for the owner (for the sidebar)."""
        owner = self._owner_for(params)
        root = self._owner_sessions_dir(owner)
        items: list[Dict[str, Any]] = []
        if root.is_dir():
            for child in root.iterdir():
                meta_path = child / "meta.json"
                if not meta_path.is_file():
                    continue
                try:
                    items.append(json.loads(meta_path.read_text(encoding="utf-8")))
                except Exception:  # noqa: BLE001 — one bad file must not hide the rest
                    continue
        items.sort(key=lambda meta: meta.get("updated_at") or "", reverse=True)
        return {"sessions": items}

    async def _command_chat_session_load(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """The transcript of one conversation (for switching sessions)."""
        owner = self._owner_for(params)
        session_id = str(params.get("session_id") or "")
        rec_dir = self._session_record_dir(owner, session_id)
        chat_path = rec_dir / "chat.jsonl"
        messages: list[Dict[str, Any]] = []
        if chat_path.is_file():
            for line in chat_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
        return {"messages": messages}

    async def _command_chat_session_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = self._owner_for(params)
        session_id = str(params.get("session_id") or "")
        rec_dir = self._session_record_dir(owner, session_id)
        if rec_dir.is_dir():
            shutil.rmtree(rec_dir, ignore_errors=True)
        return {"deleted": True}

    async def _command_chat_feedback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Append a thumbs up/down to the conversation's feedback log."""
        owner = self._owner_for(params)
        session_id = str(params.get("session_id") or "")
        rec_dir = self._session_record_dir(owner, session_id)
        rec_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "message_id": params.get("message_id"),
            "value": params.get("value"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with (rec_dir / "feedback.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"ok": True}

    async def _command_canvas_flow_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        return {"flows": canvas_manager.list_flows(self._canvas_flows_dir(session_id))}

    async def _command_canvas_flow_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        flow_id = str(params.get("flow_id") or "")
        if not flow_id:
            raise ValueError("flow_id is required")
        graph = canvas_manager.get_flow(flow_id, self._canvas_flows_dir(session_id))
        return {"flow": graph.model_dump(mode="json"), "status": canvas_manager.flow_status(graph)}

    @staticmethod
    def _parse_graph(payload: Any) -> FlowGraph:
        if not isinstance(payload, dict):
            raise ValueError("flow must be an object")
        try:
            return FlowGraph.model_validate(payload)
        except Exception as exc:
            raise ValueError(f"Invalid flow document: {exc}") from exc

    async def _command_canvas_flow_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a session draft. Drafts may be incomplete; publish validates fully."""
        session_id = self._require_session_id(params)
        session = self._sessions[session_id]
        session.sandbox.materialize()
        graph = canvas_manager.save_flow(self._parse_graph(params.get("flow")), self._canvas_flows_dir(session_id))
        await self._publish("canvas.flow.saved", graph.summary(), session_id=session_id)
        return {"flow": graph.model_dump(mode="json"), "status": canvas_manager.flow_status(graph)}

    async def _command_canvas_library_export(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export a canvas draft (JSON) into the shared reuse library under
        ``extension/canvas/``. Isolated from the agent system's HTML workflows."""
        session_id = self._require_session_id(params)
        flow_id = str(params.get("flow_id") or "")
        if not flow_id:
            raise ValueError("flow_id is required")
        result = await canvas_manager.export_to_library(flow_id, self._canvas_flows_dir(session_id))
        await self._publish("canvas.library.changed", result, session_id=session_id)
        return result

    async def _command_canvas_library_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {"flows": canvas_manager.list_library()}

    async def _command_canvas_defaults_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """Shipped example flows the picker offers as templates."""
        return {"flows": canvas_manager.list_defaults()}

    async def _command_canvas_defaults_import(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name") or "")
        if not name:
            raise ValueError("name is required")
        graph = canvas_manager.import_default(name)
        return {"flow": graph.model_dump(mode="json")}

    async def _command_canvas_library_import(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Load a library flow as a fresh draft (returns the graph; the frontend
        saves it as a new session flow)."""
        name = str(params.get("name") or "")
        if not name:
            raise ValueError("name is required")
        graph = canvas_manager.import_from_library(name)
        return {"flow": graph.model_dump(mode="json")}

    async def _command_canvas_library_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        name = str(params.get("name") or "")
        if not name:
            raise ValueError("name is required")
        deleted = await canvas_manager.delete_from_library(name)
        if deleted:
            await self._publish("canvas.library.changed", {"name": name, "deleted": True}, session_id=session_id)
        return {"name": name, "deleted": deleted}

    async def _command_canvas_flow_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        flow_id = str(params.get("flow_id") or "")
        if not flow_id:
            raise ValueError("flow_id is required")
        deleted = await canvas_manager.delete_flow(flow_id, self._canvas_flows_dir(session_id))
        return {"flow_id": flow_id, "deleted": deleted}

    async def _command_canvas_flow_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compile the posted graph and start it on the workflow runtime (draft run)."""
        session_id = self._require_session_id(params)
        graph = self._parse_graph(params.get("flow"))
        run_input = params.get("input")
        if run_input is not None and not isinstance(run_input, dict):
            raise ValueError("input must be an object")
        session = self._sessions[session_id]
        # Running saves first, so the flow has a stable id to hang its history
        # off — otherwise a draft that was never explicitly saved (every flow
        # opened from a template) vanished on refresh along with its run.
        graph = canvas_manager.save_flow(graph, self._canvas_flows_dir(session_id))
        # Steps write run output under the session's own roots.
        self._bind_runtime_to_session(session)
        run_id = await canvas_manager.run_flow(graph, input=run_input, ctx=session.context)
        self._run_sessions[run_id] = session_id
        canvas_manager.record_run(graph.id, run_id, self._canvas_runs_dir(session_id))
        await self._publish("canvas.flow.saved", {"flow_id": graph.id}, session_id=session_id)
        return {"run_id": run_id, "flow_id": graph.id, "flow": graph.model_dump(mode="json")}

    async def _command_canvas_run_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        if not run_id:
            raise ValueError("run_id is required")
        return {"run": canvas_manager.run_status(run_id)}

    async def _command_canvas_run_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Every run this flow has had, newest first — the canvas history panel."""
        session_id = self._require_session_id(params)
        flow_id = str(params.get("flow_id") or "")
        if not flow_id:
            raise ValueError("flow_id is required")
        limit = int(params.get("limit") or 50)
        return {"runs": canvas_manager.list_runs(flow_id, self._canvas_runs_dir(session_id), limit=limit)}

    async def _command_canvas_run_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        if not run_id:
            raise ValueError("run_id is required")
        return {"run_id": run_id, "cancelled": canvas_manager.cancel_run(run_id)}

    # ------------------------------------------------------------------ ide
    async def _command_ide_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start (or reuse) this session's VS Code container and say where to embed it.

        The status carries a ``path`` (``/ide/<session>/``) rather than a host:
        the editor lives on the UI's OWN origin, so whatever address the browser
        reached the UI at works — see autogenesis/ide/README.md.
        """
        session_id = self._require_session_id(params)
        session = self._sessions[session_id]
        await ide_manager.start(
            session_id,
            workspace_root=session.sandbox.workspace_root,
            owner=session.owner,
        )
        return ide_manager.status(session_id)

    async def _command_ide_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        # Doubles as the keep-alive: an open Code view pings this.
        ide_manager.touch(session_id)
        return ide_manager.status(session_id)

    async def _command_ide_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        return {"session_id": session_id, "stopped": await ide_manager.stop(session_id)}

    # -------------------------------------------------------------- science
    async def _command_science_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Bring this project's Jupyter Server up and say where the Lab lives.

        The same server the agent's code_interpreter_tool uses, so the panel,
        the REPL, the agent and JupyterLab all share ONE kernel — there is no
        second set of variables to keep in step.
        """
        session_id = self._require_session_id(params)
        session = self._sessions[session_id]
        return await science_manager.start(
            session_id, workspace_root=session.sandbox.workspace_root, owner=session.owner)

    async def _command_science_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        return science_manager.status(session_id)

    async def _command_science_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        return {"session_id": session_id, "stopped": await science_manager.stop(session_id)}

    async def _command_science_compute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """GPUs, CPU, memory and disk — this machine, which is what the kernel gets."""
        session_id = self._require_session_id(params)
        return (await science_manager.compute(session_id)).model_dump(mode="json")

    async def _command_science_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """What has run in this project's kernel, agent and user alike.

        This is the notebook the Science view shows. It is the kernel's own
        record rather than a document someone writes alongside it, which is why
        nothing can drift out of sync with what actually ran.
        """
        session_id = self._require_session_id(params)
        limit = max(1, min(int(params.get("limit") or 200), 1000))
        history = kernel_manager.history(session_id, limit=limit)
        # ``after`` is how many entries the client already holds. The panel polls
        # while the agent works, and a history carrying a few base64 figures is
        # megabytes — resending all of it every few seconds is pure waste. The
        # list is append-only, so an index is a valid cursor; ``total`` lets the
        # client notice a trim and reload instead of silently missing entries.
        after = max(0, int(params.get("after") or 0))
        fresh = history[after:] if after <= len(history) else history
        return {
            "session_id": session_id,
            "status": kernel_manager.status(session_id).model_dump(mode="json"),
            "total": len(history),
            "after": after,
            "executions": [item.model_dump(mode="json") for item in fresh],
        }

    async def _command_science_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run a cell as the user, in the same kernel the agent uses."""
        session_id = self._require_session_id(params)
        session = self._sessions[session_id]
        code = str(params.get("code") or "")
        if not code.strip():
            raise ValueError("Nothing to run")

        async def stream(output) -> None:
            # Published as it arrives, so a long cell shows its prints while it
            # runs instead of everything landing when the call returns.
            await self._publish("science.output", {"output": output.model_dump(mode="json")},
                                session_id=session_id)

        result = await kernel_manager.execute(
            code, key=session_id, workspace=str(session.sandbox.workspace_root),
            language=str(params.get("language") or "python"), origin="user", on_output=stream)
        return {
            "success": result.success, "error": result.error,
            "execution_count": result.execution_count,
            "outputs": [output.model_dump(mode="json") for output in result.outputs],
        }

    async def _command_science_interrupt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        return {"interrupted": await kernel_manager.interrupt(session_id)}

    async def _command_science_restart(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Throw the variables away. The history stays — it is what ran, not what is live."""
        session_id = self._require_session_id(params)
        return {"restarted": await kernel_manager.restart(session_id)}

    async def _command_science_notebooks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Every notebook in the project's workspace, read off disk.

        Off disk so this answers before the Jupyter Server has started and after
        it has stopped — a notebook is a workspace file, and the server is not.
        """
        session_id = self._require_session_id(params)
        owner = self._sessions[session_id].owner
        return {"session_id": session_id,
                "notebooks": [item.model_dump(mode="json")
                              for item in science_manager.notebooks(session_id, owner=owner)]}

    async def _command_science_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Write the kernel's history out as a real .ipynb.

        The panel is live history, not a document; this is how a run is kept —
        openable in JupyterLab, in the Code view, or anywhere else.
        """
        session_id = self._require_session_id(params)
        owner = self._sessions[session_id].owner
        notebook = science_manager.save_history_as_notebook(
            session_id, str(params.get("name") or "session"), owner=owner)
        return {"session_id": session_id, "notebook": notebook.model_dump(mode="json")}

    @staticmethod
    def _workflow_preview_document(source: str) -> str:
        """Build a self-contained preview for a sandboxed browser iframe.

        Persisted Workflows may reference only the framework's shared visual assets.
        A ``srcdoc`` iframe has no useful base URL for those repository-relative paths,
        so the Gateway embeds the trusted CSS and renderer without changing the stored
        executable HTML.
        """
        visual_dir = Path(__file__).resolve().parents[1] / "visual"
        assets = {
            "prompt.css": (visual_dir / "css" / "prompt.css").read_text(encoding="utf-8"),
            "workflow.css": (visual_dir / "css" / "workflow.css").read_text(encoding="utf-8"),
            "workflow.js": (visual_dir / "js" / "workflow.js").read_text(encoding="utf-8"),
        }
        document = lxml_html.document_fromstring(source)
        for link in document.xpath("//link[@rel='stylesheet']"):
            filename = Path(link.get("href", "")).name
            if filename not in assets:
                continue
            link.tag = "style"
            link.attrib.clear()
            link.text = assets[filename]
        for script in document.xpath("//script[@src]"):
            filename = Path(script.get("src", "")).name
            if filename != "workflow.js":
                continue
            script.attrib.clear()
            script.text = assets[filename]
        rendered = etree.tostring(document, encoding="unicode", method="html")
        return "<!DOCTYPE html>\n" + rendered

    async def _capability_detail(self, kind: str, name: str) -> Dict[str, Any]:
        managers = {
            "skills": skill_manager,
            "tools": tool_manager,
            "agents": agent_manager,
            "connectors": connector_manager,
            "environments": environment_manager,
        }
        if kind == "workflows":
            if not name or name not in workflow_manager.list():
                raise ValueError(f"Unknown workflows: {name}")
            spec = workflow_manager.get(name)
            assert spec is not None
            properties = {
                input_name: dict(input_spec.parameter_schema or {"type": input_spec.type})
                for input_name, input_spec in spec.inputs.items()
            }
            required = [input_name for input_name, input_spec in spec.inputs.items() if input_spec.required]
            parameter_schema: Dict[str, Any] = {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            }
            if required:
                parameter_schema["required"] = required
            document_path = None
            if spec.source_path:
                _, document_path = self._read_repository_file(
                    Path(__file__).resolve().parents[2], Path(spec.source_path),
                )
            return {
                "kind": kind,
                "name": name,
                "description": spec.description,
                "version": spec.version,
                "permission_mode": "workspace_write",
                "type": "dynamic_html",
                "enable_evolving": spec.enable_evolving,
                "actions": [],
                "parameter_schema": parameter_schema,
                "usage": f"Run workflow {name} with an input object.",
                "configuration": {},
                "editable": False,
                "document": spec.source,
                "preview_document": self._workflow_preview_document(spec.source),
                "document_path": document_path,
                "language": "html",
            }
        if kind == "commands":
            command = await command_manager.get(name)
            if command is None:
                raise ValueError(f"Unknown commands: {name}")
            return {
                "kind": kind,
                "name": name,
                "description": str(command.description),
                "version": "1.0.0",
                "permission_mode": str(command.permission_mode),
                "type": command.type.value,
                "enable_evolving": False,
                "actions": [],
                "parameter_schema": {
                    "type": "object",
                    "properties": {"args": {"type": "array", "items": {"type": "string"}}},
                    "required": [],
                },
                "usage": command.usage or f"/{command.name}",
                "configuration": {},
                "editable": False,
                "document": self._command_document(command),
                "document_path": None,
                "language": "markdown",
            }
        if kind == "canvas":
            path = canvas_manager.library_path(name)
            if not path.is_file():
                raise ValueError(f"Unknown canvas flow: {name}")
            graph = FlowGraph.model_validate_json(path.read_text(encoding="utf-8"))
            steps = len([n for n in graph.nodes if n.type == "step"])
            return {
                "kind": kind, "name": name,
                "description": graph.description or f"Canvas library flow · {steps} step(s).",
                "version": graph.version, "permission_mode": "read_only", "type": "canvas",
                "enable_evolving": False, "actions": [], "parameter_schema": {},
                "usage": "Reusable visual flow — import it into the canvas to run or edit.",
                "configuration": {}, "editable": False,
                "document": json.dumps(graph.model_dump(mode="json"), indent=2, ensure_ascii=False),
                "document_path": str(path), "language": "source",
            }
        manager = managers.get(kind)
        if manager is None:
            raise ValueError("kind must be one of: skills, tools, agents, connectors, environments, workflows, commands, canvas")
        if not name:
            raise ValueError("Capability name is required")
        if name not in await manager.list():
            raise ValueError(f"Unknown {kind}: {name}")

        info = await manager.get_info(name)
        if info is None:
            raise ValueError(f"Capability details are unavailable: {name}")

        if kind in {"tools", "agents"}:
            document, document_path, language = self._capability_usage_document(kind, name, info), None, "markdown"
        else:
            document, document_path, language = self._capability_document(kind, name, info)
        return {
            "kind": kind,
            "name": name,
            "description": str(getattr(info, "description", "")),
            "version": str(getattr(info, "version", "1.0.0")),
            "permission_mode": str(getattr(info, "permission_mode", "workspace_write")),
            "type": getattr(info, "type", None),
            "enable_evolving": bool(getattr(info, "enable_evolving", False)),
            "actions": list(getattr(info, "actions", []) or []),
            "parameter_schema": self._parameter_schema(info),
            "usage": None,
            "configuration": self._capability_configuration(kind, info),
            "editable": kind in {"tools", "skills", "agents"},
            "document": document,
            "document_path": document_path,
            "language": language,
        }

    async def _command_capability_configure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        kind = str(params.get("kind") or "")
        name = str(params.get("name") or "")
        configuration = params.get("configuration")
        if kind not in {"tools", "skills", "agents"}:
            raise ValueError("Only tools, skills, and agents have editable configuration")
        if not name:
            raise ValueError("Capability name is required")
        if not isinstance(configuration, dict):
            raise ValueError("configuration must be an object")

        if kind == "tools":
            info = await tool_manager.get_info(name)
            if info is None:
                raise ValueError(f"Unknown tools: {name}")
            tool_class = getattr(info, "cls", None) or type(getattr(info, "instance", None))
            if tool_class is type(None):
                raise ValueError(f"Tool configuration is unavailable: {name}")
            await tool_manager.update(name, tool=tool_class, config=configuration)
        elif kind == "agents":
            info = await agent_manager.get_info(name)
            if info is None or getattr(info, "cls", None) is None:
                raise ValueError(f"Agent configuration is unavailable: {name}")
            await agent_manager.update(agent_cls=info.cls, agent_config_dict=configuration)
        else:
            info = await skill_manager.get_info(name)
            if info is None:
                raise ValueError(f"Unknown skills: {name}")
            allowed = {"description", "metadata", "content"}
            unknown = set(configuration) - allowed
            if unknown:
                raise ValueError(f"Unsupported skill configuration fields: {', '.join(sorted(unknown))}")
            if "metadata" in configuration and not isinstance(configuration["metadata"], dict):
                raise ValueError("configuration.metadata must be an object")
            if "description" in configuration and not isinstance(configuration["description"], str):
                raise ValueError("configuration.description must be a string")
            if "content" in configuration and not isinstance(configuration["content"], str):
                raise ValueError("configuration.content must be a string")
            await skill_manager.update(name, **configuration)

        detail = await self._capability_detail(kind, name)
        await self._publish(
            "capability.configured",
            {"kind": kind, "name": name, "version": detail["version"]},
        )
        return detail

    async def _command_model_list(self, _: Dict[str, Any]) -> Dict[str, Any]:
        providers: Dict[str, list[Dict[str, Any]]] = {}
        for model_name in model_manager.list():
            model = model_manager.get_model_config(model_name)
            if model is None:
                continue
            providers.setdefault(model.provider, []).append(self._model_summary(model))
        return {
            "providers": [
                {"name": provider, "models": sorted(models, key=lambda model: model["name"])}
                for provider, models in sorted(providers.items())
            ]
        }

    async def _command_model_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name") or "")
        if not name:
            raise ValueError("Model name is required")
        model = model_manager.get_model_config(name)
        if model is None:
            raise ValueError(f"Unknown model: {name}")
        return {
            "model": self._model_summary(model),
            "configuration": self._safe_model_configuration(model),
            "has_api_key": bool(model.api_key),
        }

    async def _command_model_configure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        original_name = str(params.get("original_name") or "").strip()
        configuration = params.get("configuration")
        if not isinstance(configuration, dict):
            raise ValueError("configuration must be an object")

        allowed_fields = {
            "model_name", "model_type", "model_id", "provider", "api_base",
            "temperature", "reasoning", "plugins", "max_completion_tokens",
            "max_output_tokens", "supports_streaming", "supports_functions",
            "supports_vision", "output_version", "timeout", "key_pool_name",
            "fallback_model",
        }
        unknown = set(configuration) - allowed_fields
        if unknown:
            raise ValueError(f"Unsupported model configuration fields: {', '.join(sorted(unknown))}")

        existing = model_manager.get_model_config(original_name) if original_name else None
        if original_name and existing is None:
            raise ValueError(f"Unknown model: {original_name}")

        merged = existing.model_dump() if existing is not None else {}
        merged.update(configuration)
        try:
            model = ModelConfig.model_validate(merged)
        except Exception as exc:  # pydantic exposes useful validation details
            raise ValueError(f"Invalid model configuration: {exc}") from exc

        if not model.model_name.strip() or not model.model_id.strip():
            raise ValueError("model_name and model_id must not be empty")
        if model.provider not in {"openai", "openrouter", "anthropic", "google"}:
            raise ValueError(f"Unsupported provider: {model.provider}")
        conflicting = model_manager.get_model_config(model.model_name)
        if conflicting is not None and model.model_name != original_name:
            raise ValueError(f"A model named {model.model_name} is already registered")

        supplied_key = params.get("api_key")
        if supplied_key is not None and not isinstance(supplied_key, str):
            raise ValueError("api_key must be a string")
        if bool(params.get("clear_api_key")):
            model.api_key = None
        elif isinstance(supplied_key, str) and supplied_key.strip():
            model.api_key = supplied_key.strip()

        await model_manager.register_model(model)
        if original_name and original_name != model.model_name:
            await model_manager.unregister_model(original_name)

        action = "updated" if existing is not None else "created"
        await self._publish("models.changed", {"action": action, "model": self._model_summary(model)})
        return {
            "model": self._model_summary(model),
            "configuration": self._safe_model_configuration(model),
            "has_api_key": bool(model.api_key),
        }

    # ------------------------------------------------------------------
    # Playground — direct model chat over model_manager (no agent involved)
    # ------------------------------------------------------------------

    async def _command_model_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a streaming chat completion; tokens arrive as model.chat.* events."""
        session_id = self._require_session_id(params)
        model = str(params.get("model") or "")
        if not model:
            raise ValueError("model is required")
        if model_manager.get_model_config(model) is None:
            raise ValueError(f"Unknown model: {model}")
        messages = params.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant"} \
                    or not isinstance(message.get("content"), str):
                raise ValueError("each message needs a role (system/user/assistant) and string content")

        request_id = make_id()
        task = asyncio.create_task(
            self._run_model_chat(request_id, model, messages, session_id),
            name=f"model-chat-{request_id}",
        )
        self._chat_tasks[request_id] = task
        task.add_done_callback(lambda _finished: self._chat_tasks.pop(request_id, None))
        return {"request_id": request_id, "model": model}

    async def _run_model_chat(self, request_id: str, model: str, messages: list, session_id: str) -> None:
        from autogenesis.message.types import AssistantMessage, HumanMessage, SystemMessage
        from autogenesis.model.types import StreamDone, TextDelta, ThinkingDelta

        message_types = {"user": HumanMessage, "system": SystemMessage, "assistant": AssistantMessage}
        messages = [message_types[item["role"]](content=item["content"]) for item in messages]
        text_parts: list[str] = []
        usage: Optional[Dict[str, Any]] = None
        try:
            async for event in model_manager.stream(name=model, input={"messages": messages}):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    await self._publish("model.chat.delta", {"request_id": request_id, "text": event.text}, session_id=session_id)
                elif isinstance(event, ThinkingDelta):
                    await self._publish("model.chat.delta", {"request_id": request_id, "thinking": event.text}, session_id=session_id)
                elif isinstance(event, StreamDone):
                    usage = getattr(event, "usage", None)
            await self._publish(
                "model.chat.done",
                {"request_id": request_id, "message": "".join(text_parts), "usage": usage},
                session_id=session_id,
            )
        except asyncio.CancelledError:
            await self._publish("model.chat.cancelled", {"request_id": request_id, "message": "".join(text_parts)}, session_id=session_id)
            raise
        except Exception as exc:  # noqa: BLE001 — surface provider failures to the panel
            await self._publish("model.chat.error", {"request_id": request_id, "error": str(exc)}, session_id=session_id)

    async def _command_model_chat_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        request_id = str(params.get("request_id") or "")
        task = self._chat_tasks.get(request_id)
        if task is not None and not task.done():
            task.cancel()
            return {"request_id": request_id, "cancelled": True}
        return {"request_id": request_id, "cancelled": False}

    @staticmethod
    def _model_summary(model: ModelConfig) -> Dict[str, Any]:
        return {
            "name": model.model_name,
            "id": model.model_id,
            "type": model.model_type,
            "streaming": model.supports_streaming,
            "functions": model.supports_functions,
            "vision": model.supports_vision,
        }

    @staticmethod
    def _safe_model_configuration(model: ModelConfig) -> Dict[str, Any]:
        return model.model_dump(exclude={"api_key"})

    async def _command_session_capabilities_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions[self._require_session_id(params)]
        return {"capabilities": session.capabilities}

    async def _command_session_capabilities_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        requested = params.get("capabilities")
        if not isinstance(requested, dict):
            raise ValueError("capabilities must be an object")

        available = await self._available_capabilities()
        selection: Dict[str, list[str]] = {}
        for kind, names in available.items():
            requested_names = requested.get(kind, available[kind])
            if not isinstance(requested_names, list) or not all(isinstance(name, str) for name in requested_names):
                raise ValueError(f"capabilities.{kind} must be a list of names")
            invalid = set(requested_names) - set(names)
            if invalid:
                raise ValueError(f"Unknown {kind}: {', '.join(sorted(invalid))}")
            selection[kind] = list(dict.fromkeys(requested_names))

        session = self._sessions[session_id]
        session.capabilities = selection
        self._sync_session_capabilities(session)
        await self._publish("session.capabilities.updated", {"capabilities": selection}, session_id=session_id)
        return {"capabilities": selection}

    async def _command_command_execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = self._require_session_id(params)
        raw = str(params.get("raw") or "").strip()
        command_name = raw.lstrip("/").split(maxsplit=1)[0] if raw else ""
        if not command_name:
            raise ValueError("Command is required")
        session = self._sessions[session_id]
        if command_name not in {"help", "?"} and command_name not in session.capabilities.get("commands", []):
            raise ValueError(f"Command /{command_name} is disabled for this session")
        response = await command_manager.dispatch(
            raw,
            ctx=CommandContext(
                id=session_id,
                name=command_name,
                raw=raw,
                extra={
                    **session.context.extra,
                    "session_id": session_id,
                    "capabilities": session.capabilities,
                },
            ),
        )
        payload = {
            "raw": raw,
            "success": bool(response.success),
            "message": response.message,
            "data": response.data,
        }
        await self._publish("command.executed", payload, session_id=session_id)
        return payload

    async def _command_approval_respond(self, params: Dict[str, Any]) -> Dict[str, Any]:
        approval_id = str(params.get("approval_id") or "")
        if not approval_id:
            raise ValueError("approval_id is required")
        # The existing runtime does not yet expose a user-approval rendezvous.
        # Accepting the command keeps the protocol stable while permissions migrate here.
        await self._publish("approval.responded", dict(params), session_id=params.get("session_id"))
        return {"approval_id": approval_id, "accepted": True}

    def _bind_runtime_to_session(self, session: GatewaySession) -> None:
        """Point the shared runtime at ``session``'s own project roots.

        Direct entry points (``examples/run_*``, the CLI) bind their session before
        any manager initializes, so every manager derives session-scoped paths from
        config.  The Gateway cannot: it initializes one shared runtime at startup,
        before any session exists.  Binding here — on the single, serialized task
        path (the task queue runs one worker) — gives the same result: config roots
        and the managers that persist run output all move under
        ``output/<owner>/sessions/<session-id>/`` for the duration of this task.
        """
        if self._bound_session_id == session.context.id:
            return
        # Work is about to happen in this session — create its roots now.
        session.sandbox.materialize()
        # …and record enough to find this session again after a restart. Written
        # here rather than at session.create so an idle session that never ran
        # anything still leaves no directory behind, and so what is restorable is
        # exactly what has real work in it.
        self._write_session_manifest(session)
        bind_session_roots(config, session.sandbox)
        # Managers cached their base_dir at initialize(); re-point the ones that
        # persist per-run output. Writers that read config at write time (the
        # snapshot hook) follow the rebound config automatically.
        trace_manager.rebind(config.log_root)
        memory_manager.rebind(config.log_root)
        trajectory_manager.rebind(config.log_root)
        task_manager.rebind(os.path.join(config.log_root, "tasks"))
        # Boot ran without a file sink (no session existed yet); attach it now so the
        # run log lands in this session too.
        logger.rebind(config.log_path)
        self._bound_session_id = session.context.id
        logger.info(f"| 📁 Runtime bound to session {session.context.id}: {config.log_root}")

    async def _run_task(self, record: TaskRecord) -> Any:
        session_id = record.task.session_id
        if not session_id or session_id not in self._sessions:
            raise RuntimeError(f"Gateway session is unavailable for task {record.task.id}")
        session = self._sessions[session_id]
        self._bind_runtime_to_session(session)
        self._sync_session_capabilities(session)
        conversation_id = str((record.task.metadata or {}).get("conversation_id") or "")
        # The agent runs under its conversation, not its project: ctx.id is the
        # scope of memory, token budget and todos, and two lines of dialogue in
        # one project must not inherit each other's. Resources keyed elsewhere
        # (the workspace, any container) stay shared — they hang off config.
        ctx = session.context.model_copy(update={"id": conversation_id}) if conversation_id else session.context
        self._run_conversations[record.task.id] = conversation_id
        await self._publish("task.started", {"content": record.task.content},
                            session_id=session_id, conversation_id=conversation_id, task_id=record.task.id)
        agent_task = asyncio.create_task(
            agent_manager(
                name="meta_agent",
                input={
                    "task": record.task.content,
                    "files": record.task.files,
                    "capabilities": session.capabilities,
                    "task_id": record.task.id,
                },
                ctx=ctx,
            ),
            name=f"gateway-agent-{record.task.id}",
        )
        self._active_agent_tasks[record.task.id] = agent_task
        try:
            response = await agent_task
            payload = response.model_dump(mode="json") if hasattr(response, "model_dump") else {"result": str(response)}
            await self._publish("task.completed", payload, session_id=session_id,
                                conversation_id=conversation_id, task_id=record.task.id)
            return response
        except asyncio.CancelledError:
            await self._publish("task.cancelled", {}, session_id=session_id,
                                conversation_id=conversation_id, task_id=record.task.id)
            raise
        except Exception as exc:
            await self._publish("task.failed", {"error": str(exc)}, session_id=session_id,
                                conversation_id=conversation_id, task_id=record.task.id)
            raise
        finally:
            self._active_agent_tasks.pop(record.task.id, None)
            self._run_conversations.pop(record.task.id, None)

    async def _on_trace_event(self, event) -> None:
        payload = event.to_dict()
        # A trace belongs to whichever conversation submitted the task that
        # produced it. Work with no conversation (a canvas flow) carries none,
        # which is what keeps it out of the chat transcript.
        await self._publish("trace.event", payload, session_id=event.session_id,
                            conversation_id=self._run_conversations.get(event.task_id or ""),
                            task_id=event.task_id)
        # A workflow run (canvas draft run) just finished. Push an explicit
        # terminal so canvas clients resolve immediately instead of discovering
        # it by polling canvas.run.status (which can be missed/dropped). The
        # trace's task_id IS the run_id; the client matches it to its live run.
        if payload.get("event_type") == "workflow_end" and event.task_id:
            # Report the run's real terminal state (a cancelled run is not "failed").
            # Clients re-fetch canvas.run.status for the authoritative record, so this
            # is a hint; fall back to the trace's success flag if the run is gone.
            run = workflow_manager.get_run(event.task_id)
            state = getattr(getattr(run, "state", None), "value", None) if run else None
            await self._publish(
                "canvas.run.ended",
                {"run_id": event.task_id, "state": state or ("succeeded" if payload.get("success") else "failed")},
                # A run executes under its own context, so the trace carries the
                # run id here, not the session the user is watching. Route it
                # back to whoever asked for the run.
                session_id=self._run_sessions.get(event.task_id, event.session_id),
                task_id=event.task_id,
            )

    async def _on_environment_view(self, view) -> None:
        """Republish an environment live-view to the client watching the active session.

        Tasks run serially, so the environment producing this view belongs to the
        currently bound session — scope the event to it (the view's own session_id
        is a sub-agent id the browser client would not match on).
        """
        payload = view.model_dump(mode="json")
        # For a VNC live view, keep the raw ephemeral websockify target server-side
        # and hand the client a same-origin relative path instead. The client
        # resolves it against the gateway origin and connects via /env/vnc, which
        # the gateway relays to this target — so only the UI port is ever exposed.
        if payload.get("type") == "vnc" and payload.get("url"):
            self._latest_vnc_target = payload["url"]
            payload["url"] = "/env/vnc"
        await self._publish("environment.view", payload, session_id=self._bound_session_id)

    async def _on_extension_change(self, change: Dict[str, str]) -> None:
        """Publish registry changes so connected clients see evolved components immediately."""
        kind_by_module = {
            "tool": "tools",
            "agent": "agents",
            "skill": "skills",
            "connector": "connectors",
            "environment": "environments",
        }
        kind = kind_by_module.get(change.get("module", ""))
        name = change.get("name")
        if not kind or not name:
            return

        available = await self._available_capabilities()
        action = change.get("action", "updated")
        is_available = name in available[kind]
        for session_id, session in self._sessions.items():
            current = [entry for entry in session.capabilities.get(kind, []) if entry in available[kind]]
            if action == "registered" and is_available:
                updated = list(dict.fromkeys([*current, name]))
            else:
                updated = current
            session.capabilities[kind] = updated
            self._sync_session_capabilities(session)
            await self._publish(
                "session.capabilities.updated",
                {"capabilities": session.capabilities},
                session_id=session_id,
            )

        await self._publish(
            "capabilities.changed",
            {
                "action": action,
                "kind": kind,
                "name": name,
                "version": change.get("version"),
                "capabilities": available,
            },
        )

    async def _publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GatewayEvent:
        # Sequence per conversation where there is one: two dialogues in the
        # same project run independently, so a shared counter would make each
        # one's replay depend on how busy the other had been.
        key = conversation_id or session_id or "_gateway"
        self._sequence[key] += 1
        event = GatewayEvent(
            type=event_type,
            payload=payload,
            session_id=session_id,
            conversation_id=conversation_id,
            task_id=task_id,
            seq_no=self._sequence[key],
        )
        self._events[key].append(event)
        self._append_event_log(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow clients reconnect and recover through session.events.
                self._subscribers.discard(queue)
        return event

    def _require_session_id(self, params: Dict[str, Any]) -> str:
        session_id = str(params.get("session_id") or "")
        if not session_id:
            raise ValueError("session_id is required")
        if session_id not in self._sessions:
            raise ValueError(f"Unknown session: {session_id}")
        return session_id

    async def _available_capabilities(self) -> Dict[str, list[str]]:
        return {
            "agents": await agent_manager.list(),
            "tools": await tool_manager.list(),
            "skills": await skill_manager.list(),
            "connectors": await connector_manager.list(),
            "environments": await environment_manager.list(),
            "workflows": workflow_manager.list(),
            "commands": await command_manager.list(),
            # Canvas flows: shipped default templates + the user's reuse library.
            "canvas": canvas_manager.list_default_names() + canvas_manager.list_library_names(),
        }

    def _capability_document(self, kind: str, name: str, info: Any) -> tuple[str, Optional[str], str]:
        repository_root = Path(__file__).resolve().parents[2]
        if kind == "skills":
            path = Path(str(getattr(info, "skill_dir", ""))) / "SKILL.md"
            content, relative_path = self._read_repository_file(repository_root, path)
            return content or str(getattr(info, "content", "")), relative_path, "markdown"
        if kind == "connectors":
            path = Path(str(getattr(info, "connector_dir", ""))) / "CONNECTOR.md"
            content, relative_path = self._read_repository_file(repository_root, path)
            return content or str(getattr(info, "content", "")), relative_path, "markdown"
        if kind == "environments":
            env_class = getattr(info, "cls", None)
            source_file = getattr(env_class, "__source_file__", None)
            if not source_file and env_class is not None:
                try:
                    from inspect import getfile
                    source_file = getfile(env_class)
                except (TypeError, OSError):
                    source_file = None
            if source_file:
                path = Path(str(source_file)).parent / "ENVIRONMENT.md"
                content, relative_path = self._read_repository_file(repository_root, path)
                if content:
                    return content, relative_path, "markdown"
            return str(getattr(info, "rules", "")), None, "markdown"

        source_path = getattr(info, "path", None)
        if source_path:
            content, relative_path = self._read_repository_file(repository_root, Path(str(source_path)))
            if content:
                return content, relative_path, "python"
        code = getattr(info, "code", None)
        if code:
            return str(code), None, "python"

        directory = "tool" if kind == "tools" else "agent"
        basename = name.removesuffix("_tool") if kind == "tools" else name
        matches = sorted((repository_root / "autogenesis" / directory).rglob(f"{basename}.py"))
        for path in matches:
            content, relative_path = self._read_repository_file(repository_root, path)
            if content:
                return content, relative_path, "python"
        return self._fallback_document(kind, name, info), None, "markdown"

    @staticmethod
    def _capability_usage_document(kind: str, name: str, info: Any) -> str:
        """Create a readable guide for callable capabilities, never a raw schema dump."""
        description = str(getattr(info, "description", "") or "No description is available.")
        instruction = str(getattr(info, "instruction", "") or "").strip()
        label = "tool" if kind == "tools" else "agent"
        lines = [
            "## What it does",
            description,
            "",
            "## How to use it",
        ]
        if instruction:
            lines.append(instruction)
        elif kind == "tools":
            lines.append(f"Enable **{name}** for the session. Autogenesis calls it when the task requires this action.")
        else:
            lines.append(f"Enable **{name}** for the session. Autogenesis can delegate suitable work to this specialist agent.")
        lines.extend([
            "",
            "## Session availability",
            f"Use the toggle in the {label} list to allow or disallow it for this session.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _sync_session_capabilities(session: GatewaySession) -> None:
        session.context.extra["capabilities"] = session.capabilities
        for kind, context_key in {
            "tools": "tool_allowlist",
            "skills": "skill_allowlist",
            "agents": "agent_allowlist",
            "connectors": "connector_allowlist",
            "environments": "environment_allowlist",
            "workflows": "workflow_allowlist",
        }.items():
            session.context.extra[context_key] = list(session.capabilities.get(kind, []))

    @staticmethod
    def _capability_configuration(kind: str, info: Any) -> Dict[str, Any]:
        if kind in {"tools", "agents"}:
            configuration = getattr(info, "config", None)
            return dict(configuration) if isinstance(configuration, dict) else {}
        if kind == "skills":
            metadata = getattr(info, "metadata", None)
            return {
                "description": str(getattr(info, "description", "")),
                "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                "content": str(getattr(info, "content", "")),
            }
        return {}

    @staticmethod
    def _command_document(command: Any) -> str:
        """Render human-facing command help instead of exposing transport schemas."""
        usage = str(getattr(command, "usage", "") or f"/{command.name}")
        examples = [f"`{usage.split()[0]}`"]
        argument_values = {
            "type": "tool",
            "name": "bash_tool",
            "version": "1.0.0",
            "label": "before-evolution",
            "new_name": "my_copy",
            "goal...": "Improve reliability for invalid input.",
        }
        expanded = []
        for token in usage.split():
            required = token.startswith("<") and token.endswith(">")
            optional = token.startswith("[") and token.endswith("]")
            if not required and not optional:
                expanded.append(token)
                continue
            key = token[1:-1]
            value = argument_values.get(key)
            if value:
                expanded.append(value)
        full_example = " ".join(expanded)
        if full_example and full_example != usage.split()[0]:
            examples.append(f"`{full_example}`")

        return "\n".join([
            "## What it does",
            str(getattr(command, "description", "No description is available.")),
            "",
            "## Usage",
            f"`{usage}`",
            "",
            "## Run it",
            "Enter an enabled command in the chat composer and press Enter. Commands run against the current session.",
            "",
            "## Examples",
            *[f"- {example}" for example in examples],
        ])

    @staticmethod
    def _parameter_schema(info: Any) -> Optional[Dict[str, Any]]:
        function_calling = getattr(info, "function_calling", None)
        if isinstance(function_calling, dict):
            parameters = function_calling.get("parameters")
            if isinstance(parameters, dict):
                return parameters
        args_schema = getattr(info, "args_schema", None)
        if args_schema is not None and hasattr(args_schema, "model_json_schema"):
            try:
                schema = args_schema.model_json_schema()
                return schema if isinstance(schema, dict) else None
            except Exception:  # noqa: BLE001
                return None
        return None

    @staticmethod
    def _fallback_document(kind: str, name: str, info: Any) -> str:
        description = str(getattr(info, "description", "No description is available."))
        instruction = str(getattr(info, "instruction", ""))
        return f"# {name}\n\n**Kind:** {kind}\n\n{description}\n" + (f"\n## Instructions\n\n{instruction}\n" if instruction else "")

    @staticmethod
    def _read_repository_file(repository_root: Path, path: Path) -> tuple[str, Optional[str]]:
        try:
            resolved = path.expanduser().resolve()
            relative_path = resolved.relative_to(repository_root)
            if not resolved.is_file():
                return "", None
            return resolved.read_text(encoding="utf-8")[:200_000], str(relative_path)
        except (OSError, UnicodeDecodeError, ValueError):
            return "", None
