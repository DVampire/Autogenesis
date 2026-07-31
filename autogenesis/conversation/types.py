"""Type definitions for the conversation module.

A **conversation** is one line of dialogue inside a project. It is the middle
level of three:

===============  =========================================  ==================
Level            Owns                                       Identified by
===============  =========================================  ==================
project          workspace files, kernels, containers        ``session_id``
**conversation** transcript, agent memory, budgets, todos    ``conversation_id``
task             one submission's trajectory and traces      ``task_id``
===============  =========================================  ==================

The split matters because the two halves scale differently. A project's files
and kernels are *resources*: one set, shared by every view and every dialogue
in it. Memory and budgets are *state*: they must not leak between lines of
work, or a fresh question inherits the last one's context and spends its
tokens.

That is why ``ctx.id`` — the scope of everything an agent accumulates — is a
conversation id, while anything that costs a container stays keyed by project.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.utils import make_id

#: Which view a conversation belongs to. The transcript is the same shape in
#: each; the view decides what is rendered beside it (files, a canvas, a
#: notebook) and lets the sidebar list one view's dialogues on their own.
ConversationView = Literal["chat", "science", "canvas"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Conversation(BaseModel):
    """One line of dialogue in a project."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=make_id, description="Unique conversation id.")
    session_id: str = Field(description="The project this conversation belongs to.")
    view: ConversationView = Field(default="chat", description="Which view opened it.")
    #: Taken from the first message rather than asked for. A dialogue that has
    #: to be named before it starts is a dialogue nobody names.
    title: str = Field(default="", description="Human label, derived from the opening message.")
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    task_ids: List[str] = Field(default_factory=list, description="Submissions made in this conversation.")

    #: Set for the record that adopted a pre-conversation transcript, so the
    #: migration is visible rather than silently rewriting history.
    migrated: bool = Field(default=False)

    def summary(self) -> Dict[str, Any]:
        """What the sidebar needs to list this conversation."""
        return {
            "conversation_id": self.id,
            "session_id": self.session_id,
            "view": self.view,
            "title": self.title or "New conversation",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "task_count": len(self.task_ids),
        }

    def touch(self) -> None:
        self.updated_at = _now()


#: How much of the opening message becomes the title.
TITLE_LIMIT = 60


def title_from(text: str) -> str:
    """Derive a conversation title from its opening message.

    Sessions used to be named ``web`` or ``interactive`` by whoever created
    them, so a sidebar of ten of them said nothing about any of them.
    """
    line = " ".join((text or "").split())
    if len(line) <= TITLE_LIMIT:
        return line
    return line[:TITLE_LIMIT].rstrip() + "…"


__all__ = ["Conversation", "ConversationView", "title_from", "TITLE_LIMIT"]
