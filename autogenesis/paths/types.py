"""Layout keys and the table they index."""

from __future__ import annotations

from enum import Enum
from typing import Dict


class P(str, Enum):
    """Keys into :data:`LAYOUT`.

    An enum rather than bare strings so a typo is a static error with editor
    completion, instead of a path containing a literal ``{owner}`` discovered
    much later.
    """

    # --- the two buckets -------------------------------------------------
    OUTPUT = "output"
    EXTENSION = "extension"
    #: One module's shared components — ``extension/skill``, ``extension/tool``,
    #: ``extension/canvas``, … Parameterised rather than one key per module,
    #: because the extension manager promotes any module type through the same
    #: path.
    EXTENSION_MODULE = "extension_module"

    # --- machine-level runtime state (belongs to the host, not a user) ---
    RUNTIME = "runtime"
    PORTS = "ports"
    LEDGER = "ledger"
    DEPLOY = "deploy"
    CHECKPOINTS = "checkpoints"
    STAGING = "staging"
    #: Where output lands before anything binds a session — the gateway's own
    #: startup logs, or a direct run that never opened one.
    UNBOUND = "unbound"

    # --- per owner (durable, survives every session) ---------------------
    OWNER = "owner"
    OWNER_STATE = "owner_state"
    OWNER_FILES = "owner_files"
    OWNER_IDE = "owner_ide"
    IDE_EXTENSIONS = "ide_extensions"
    IDE_HOME = "ide_home"
    #: $HOME for the Science workstation: pip installs, wandb logins and
    #: Jupyter settings, kept per owner so they outlive a reaped container.
    SCIENCE_HOME = "science_home"

    # --- per session / per run (disposable) ------------------------------
    SESSIONS = "sessions"
    SESSION = "session"
    SESSION_WORKSPACE = "session_workspace"
    SESSION_MANIFEST = "session_manifest"
    #: Canvas drafts belong to the session that drew them; a finished flow is
    #: promoted to the shared library under ``extension/canvas``.
    SESSION_FLOWS = "session_flows"
    #: One append-only index per flow: every run it has had, newest last.
    SESSION_RUNS = "session_runs"
    #: One conversation's transcript, append-only. The in-memory buffer is
    #: bounded and dies with the process; this is what lets a restored project
    #: reopen with its conversations instead of an empty transcript.
    CONVERSATION_EVENTS = "conversation_events"
    #: A conversation's identity: title, which view it belongs to, timestamps.
    CONVERSATION_META = "conversation_meta"
    #: All conversations of one project.
    CONVERSATIONS = "conversations"
    #: Editor state — open tabs, layout. Per session, unlike the extensions and
    #: agent logins beside it, which are worth sharing across all of them.
    SESSION_IDE_USER_DATA = "session_ide_user_data"
    #: Notebooks the Science view writes. Under the workspace, not beside it, so
    #: bash and code_interpreter — which start in the workspace — can open the
    #: same files the notebook wrote, and the files pane lists them.
    SESSION_NOTEBOOKS = "session_notebooks"
    RUN = "run"


#: The complete tree, relative to the project directory. Two roots only:
#: ``output/`` for generated, machine- and user-specific state, and
#: ``extension/`` for shared, durable components. Everything the framework
#: writes is declared here — this table *is* the disk contract.
LAYOUT: Dict[P, str] = {
    P.OUTPUT: "output",
    P.EXTENSION: "extension",
    P.EXTENSION_MODULE: "extension/{module}",

    P.RUNTIME: "output/.runtime",
    P.PORTS: "output/.runtime/ports.json",
    P.LEDGER: "output/.runtime/sandbox_ledger.json",
    P.DEPLOY: "output/.runtime/deploy",
    P.CHECKPOINTS: "output/.runtime/checkpoints",
    P.STAGING: "output/.runtime/staging/{project_key}",
    P.UNBOUND: "output/.runtime/unbound",

    P.OWNER: "output/{owner}",
    P.OWNER_STATE: "output/{owner}/state",
    P.OWNER_FILES: "output/{owner}/state/files",
    P.OWNER_IDE: "output/{owner}/state/ide",
    P.IDE_EXTENSIONS: "output/{owner}/state/ide/extensions",
    P.IDE_HOME: "output/{owner}/state/ide/home",
    P.SCIENCE_HOME: "output/{owner}/state/science/home",

    P.SESSIONS: "output/{owner}/sessions",
    P.SESSION: "output/{owner}/sessions/{session_id}",
    P.SESSION_WORKSPACE: "output/{owner}/sessions/{session_id}/workspace",
    P.SESSION_MANIFEST: "output/{owner}/sessions/{session_id}/session.json",
    P.SESSION_FLOWS: "output/{owner}/sessions/{session_id}/flows",
    P.SESSION_RUNS: "output/{owner}/sessions/{session_id}/runs",
    P.CONVERSATIONS: "output/{owner}/sessions/{session_id}/conversations",
    P.CONVERSATION_EVENTS: "output/{owner}/sessions/{session_id}/conversations/{conversation_id}.jsonl",
    P.CONVERSATION_META: "output/{owner}/sessions/{session_id}/conversations/{conversation_id}.json",
    P.SESSION_IDE_USER_DATA: "output/{owner}/sessions/{session_id}/ide/user-data",
    P.SESSION_NOTEBOOKS: "output/{owner}/sessions/{session_id}/workspace/notebooks",
    P.RUN: "output/{owner}/runs/{run_id}",
}

__all__ = ["P", "LAYOUT"]
