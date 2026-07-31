"""ConstraintHook — centralizes per-step resource-budget enforcement.

Fires on PRE_STEP. Runs every constraint the calling agent declared, BLOCKs the
step when any budget is exhausted, and returns the budget snapshot for the
agent to render into its next prompt.

This replaces the identical constraint-check block that used to be inlined in
every agent's ``_think_and_act``. Enforcement is a cross-cutting concern, so it
lives here at the step boundary — not inside message formatting. The agent
still owns its per-task token accounting (it computes ``check_input`` and pops
pending tokens before firing the hook) and its own teardown on a violation.

Expected PRE_STEP payload::

    {
        "event": HookEvent.PRE_STEP,
        "agent_name": str,
        "task_id": str,
        "constraint_names": [str, ...],   # the agent's own constraints
        "check_input": {"token", "max_step", "max_token", "max_second"},
    }

Returns ``HookResult.block(reason)`` on the first exhausted budget, otherwise
``HookResult(constraint_status=[...])`` with one status dump per constraint.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autogenesis.hook.types import Hook, HookContext, HookEvent, HookResult
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class ConstraintHook(Hook):
    """Checks resource budgets on PRE_STEP; blocks the step when a limit is exceeded."""

    name: str = "constraint_hook"
    description: str = "Enforces per-step resource budgets and reports the remaining budget."
    events: list = []
    priority: int = 1

    async def handle(self, ctx: HookContext) -> HookResult:
        """Check every declared resource budget on PRE_STEP and gate the step.

        Ignores non-PRE_STEP events. For each constraint the agent declared, runs
        it against ``check_input``; the first exhausted budget blocks the step,
        otherwise the collected per-constraint status snapshots are returned for
        the agent to render into its next prompt.

        Args:
            ctx: Hook context whose ``input`` carries ``event``, ``task_id``,
                ``constraint_names`` and ``check_input``.

        Returns:
            ``HookResult.block(reason)`` on the first exhausted budget, otherwise
            ``HookResult(constraint_status=[...])`` (ALLOW for irrelevant events).
        """
        inp = ctx.input or {}
        if inp.get("event") != HookEvent.PRE_STEP:
            return HookResult.allow()

        names: List[str] = inp.get("constraint_names") or []
        if not names:
            return HookResult.allow()

        from autogenesis.constraint.server import constraint_manager
        from autogenesis.constraint.types import ConstraintContext

        task_id = inp.get("task_id") or ctx.id
        check_input: Dict[str, Any] = inp.get("check_input") or {}
        constraint_ctx = ConstraintContext(id=task_id)

        statuses: List[Dict[str, Any]] = []
        for name in names:
            violation = await constraint_manager(name, check_input, constraint_ctx)
            if not violation.success:
                # Budget exhausted — block the step. The agent does its own
                # cleanup/stop using `reason`.
                return HookResult.block(violation.message)
            if violation.data and violation.data.get("status"):
                statuses.append(violation.data["status"])

        return HookResult(constraint_status=statuses)
