---
name: conversation
description: "Lines of dialogue inside a project — their transcripts and their identity. The middle of three levels: a project owns files and containers, a conversation owns memory and budgets, a task owns one submission."
version: 1.0.0
type: module
category: infrastructure
requirements: []
metadata: {}
---
# Conversation

A **conversation** is one line of dialogue inside a project. It sits between
the project and the task:

| Level | Owns | Identified by |
|---|---|---|
| project | workspace files, kernels, containers | `session_id` |
| **conversation** | transcript, agent memory, budgets, todos | `conversation_id` |
| task | one submission's trajectory and traces | `task_id` |

```python
from autogenesis.conversation import conversation_manager

c = conversation_manager.create(owner, session_id, view="science")
conversation_manager.note_task(owner, session_id, c.id, task_id, "run a simulation")
conversation_manager.events(owner, session_id, c.id)
```

## Why the middle level exists

The two halves of a project scale differently.

Files and kernels are **resources**: one set, shared by every view and every
dialogue. Duplicating them per dialogue would mean a container per question.

Memory, token budgets and todos are **state**: they must not leak between
lines of work, or a fresh question arrives carrying the last one's context and
spending its tokens.

Before this split both hung off the same id, so there was no way to have the
first without the second. `ctx.id` is a conversation id now — it is the scope
of everything an agent accumulates — while anything that costs a container
stays keyed by project.

## The transcript is the file

`conversations/<id>.jsonl` is append-only and unbounded, and it is what
`conversation.events` reads. The Gateway's in-memory buffer only serves live
clients: it is capped and dies with the process, so a restored project would
otherwise reopen with an empty transcript over its own files.

`<id>.json` beside it holds the identity — title, view, timestamps, the tasks
submitted in it. The title comes from the opening message rather than a prompt:
sessions used to be named `web` or `interactive` by whoever created them, and a
sidebar of ten of them said nothing about any of them.

## Views

A conversation records which view opened it (`chat` / `science` / `canvas`).
The transcript is the same shape in each; the view decides what is rendered
beside it and lets a sidebar list one view's dialogues on their own.
