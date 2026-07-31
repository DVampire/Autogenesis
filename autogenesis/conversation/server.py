"""Conversation Manager Server

Stores the dialogue lines of a project: their identity and their transcripts.

Deliberately file-backed and stateless-per-call, like the canvas manager: the
Gateway owns the live sessions, and a conversation is just a record under one
of them. Everything is written where ``autogenesis.paths`` says, so a project
directory stays self-describing — you can read a conversation off disk without
the Gateway running.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from autogenesis.conversation.types import Conversation, title_from
from autogenesis.logger import logger
from autogenesis.paths import P, path_manager


class ConversationManagerServer:
    """Create, list, and record the dialogue lines of a project."""

    # ------------------------------------------------------------------ paths
    @staticmethod
    def _meta_path(owner: str, session_id: str, conversation_id: str):
        return path_manager.get(P.CONVERSATION_META, owner=owner, session_id=session_id,
                                conversation_id=conversation_id)

    @staticmethod
    def _events_path(owner: str, session_id: str, conversation_id: str):
        return path_manager.get(P.CONVERSATION_EVENTS, owner=owner, session_id=session_id,
                                conversation_id=conversation_id)

    # ----------------------------------------------------------- lifecycle
    def create(self, owner: str, session_id: str, *, view: str = "chat",
               title: str = "", conversation_id: Optional[str] = None) -> Conversation:
        """Open a new line of dialogue in a project."""
        conversation = Conversation(session_id=session_id, view=view, title=title,
                                    **({"id": conversation_id} if conversation_id else {}))
        self.save(owner, conversation)
        logger.info(f"| 💬 Conversation opened: {conversation.id} ({view}) in {session_id}")
        return conversation

    def save(self, owner: str, conversation: Conversation) -> Conversation:
        """Persist a conversation's identity (not its transcript)."""
        path = self._meta_path(owner, conversation.session_id, conversation.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(conversation.model_dump(mode="json"), indent=2,
                                        ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        return conversation

    def get(self, owner: str, session_id: str, conversation_id: str) -> Optional[Conversation]:
        path = self._meta_path(owner, session_id, conversation_id)
        if not path.is_file():
            return None
        try:
            return Conversation.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — one bad record must not hide the rest
            logger.warning(f"| ⚠️ Unreadable conversation {path.name}: {exc}")
            return None

    def list(self, owner: str, session_id: str, *, view: Optional[str] = None) -> List[Conversation]:
        """This project's conversations, most recently used first."""
        directory = path_manager.get(P.CONVERSATIONS, owner=owner, session_id=session_id)
        if not directory.is_dir():
            return []
        out: List[Conversation] = []
        for path in directory.glob("*.json"):
            conversation = self.get(owner, session_id, path.stem)
            if conversation is not None and (view is None or conversation.view == view):
                out.append(conversation)
        out.sort(key=lambda item: item.updated_at, reverse=True)
        return out

    def rename(self, owner: str, session_id: str, conversation_id: str, title: str) -> Optional[Conversation]:
        conversation = self.get(owner, session_id, conversation_id)
        if conversation is None:
            return None
        conversation.title = title
        conversation.touch()
        return self.save(owner, conversation)

    def delete(self, owner: str, session_id: str, conversation_id: str) -> bool:
        """Remove a conversation and its transcript. True if one was there."""
        meta = self._meta_path(owner, session_id, conversation_id)
        events = self._events_path(owner, session_id, conversation_id)
        found = meta.is_file()
        for path in (meta, events):
            if path.is_file():
                path.unlink()
        return found

    # ------------------------------------------------------------ transcript
    def append(self, owner: str, session_id: str, conversation_id: str, event: Dict[str, Any]) -> None:
        """Add one event to a conversation's transcript.

        Append-only and unbounded on purpose: this is the record of what
        happened, and the Gateway's in-memory buffer is neither.
        """
        path = self._events_path(owner, session_id, conversation_id)
        if not path.parent.is_dir():
            return  # the project has not materialized yet; nothing to record against
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 — recording must never break the run
            logger.warning(f"| ⚠️ Could not append to conversation {conversation_id}: {exc}")

    def events(self, owner: str, session_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        """A conversation's transcript, oldest first."""
        path = self._events_path(owner, session_id, conversation_id)
        if not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 — one bad line must not hide the rest
                continue
        return out

    def note_task(self, owner: str, session_id: str, conversation_id: str,
                  task_id: str, content: str) -> Optional[Conversation]:
        """Record a submission against its conversation, titling it if new."""
        conversation = self.get(owner, session_id, conversation_id)
        if conversation is None:
            return None
        if task_id not in conversation.task_ids:
            conversation.task_ids.append(task_id)
        if not conversation.title:
            conversation.title = title_from(content)
        conversation.touch()
        return self.save(owner, conversation)


# Global conversation manager instance
conversation_manager = ConversationManagerServer()

__all__ = ["ConversationManagerServer", "conversation_manager"]
