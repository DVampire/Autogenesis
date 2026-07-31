"""No-progress guard policy for Agent action rounds.

The hook is deliberately stateless.  Per-run evidence belongs to ``_AgentRun`` so
concurrent sessions cannot affect one another; the hook only compares the proposed
batch with that evidence and returns a lifecycle decision.

Scope: this guard is universal, not per-agent.  It is invoked from the base
``Agent._prepare_round`` (see ``agent/types.py``), which sits on the single round
path every agent's reasoning loop flows through.  Every agent therefore inherits it
automatically -- code/general/browser/reviewer actors, the generator/evaluator/
optimizer agents, and ``ProceduralAgent`` -- with no per-agent opt-in.  ``MetaAgent``
overrides ``_prepare_round`` only to add orchestration, still chaining to ``super()``
so the guard is never bypassed.  (Contrast the read-only guard on evaluator agents,
``_allow_read_only_tool_call``, which *is* per-agent opt-in.)
"""

from __future__ import annotations

from typing import Any, Dict, List

from autogenesis.hook.types import Hook, HookContext, HookEvent, HookResult
from autogenesis.registry import HOOK


_ALWAYS_ALLOW = {
    "done_tool", "escalate_tool", "reply_tool", "todo_tool", "write_file_tool",
    "edit_file_tool", "deploy_tool", "evolution_tool",
}
_POLLING_MARKERS = ("wait", "poll", "monitor", "status", "watch")
_EXTERNAL_MARKERS = ("search", "fetch", "download", "http", "browser")
_EXTERNAL_KINDS = {"connector", "environment", "env", "workflow"}


def progress_policy(action: Dict[str, Any]) -> str:
    """Return the conservative default policy for an action.

    ``policy`` may be supplied explicitly by future capability metadata.  Until
    then, mutating/control calls and external/polling calls are allowed; stable
    workspace observations and completed sub-agent calls are guardable.
    """
    explicit = action.get("policy")
    if explicit in {"workspace", "external", "polling", "always"}:
        return explicit
    name = str(action.get("name") or "")
    kind = str(action.get("kind") or "tool")
    if name in _ALWAYS_ALLOW:
        return "always"
    if any(marker in name for marker in _EXTERNAL_MARKERS):
        return "external"
    if kind in _EXTERNAL_KINDS or any(marker in name for marker in _POLLING_MARKERS):
        return "external" if kind in _EXTERNAL_KINDS else "polling"
    return "workspace"


@HOOK.register_module(force=True)
class NoProgressHook(Hook):
    """Block a batch whose successful evidence is still valid and unchanged."""

    name: str = "no_progress_hook"
    description: str = "Prevents unchanged successful Agent actions from running again."
    events: list = []
    priority: int = 5

    async def handle(self, ctx: HookContext) -> HookResult:
        inp = ctx.input or {}
        if inp.get("event") != HookEvent.PRE_ACTION:
            return HookResult.allow()

        workspace_fingerprint = inp.get("workspace_fingerprint")
        evidence: Dict[str, Dict[str, Any]] = inp.get("evidence") or {}
        repeated: List[str] = []
        for action in inp.get("actions") or []:
            if progress_policy(action) != "workspace":
                continue
            previous = evidence.get(str(action.get("signature") or ""))
            if previous and previous.get("success") and (
                previous.get("workspace_fingerprint") == workspace_fingerprint
            ):
                repeated.append(str(action.get("name") or "action"))

        if not repeated:
            return HookResult.allow()
        names = ", ".join(repeated)
        return HookResult.block(
            "No-progress guard: successful unchanged action(s) already supplied the "
            f"same evidence: {names}. Re-inspecting state that has not changed (re-reading "
            "the same file, re-listing the same directory) will keep being blocked and "
            "wastes your step budget. Take a state-CHANGING action instead — run/execute "
            "the code you have, edit a file, or dispatch a different capability — or, if "
            "the acceptance conditions in Memory are already met, call done_tool now. "
            "Escalate only if you are truly blocked."
        )
