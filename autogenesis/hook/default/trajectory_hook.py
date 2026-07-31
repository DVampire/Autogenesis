"""TrajectoryHook — projects agent lifecycle events into a training trajectory.

Sibling of TraceHook: where TraceHook emits a raw observability event log,
TrajectoryHook feeds ``trajectory_manager`` a step-aggregated, reward-annotated
view suitable for SFT / RL export. It is dispatched by name from the run loop
(``hook_manager(name="trajectory_hook", ...)``) at ON_START / POST_ACTION /
POST_STEP / ON_STOP, mirroring how snapshot_hook is called.
"""

from __future__ import annotations

from autogenesis.config import config
from autogenesis.hook.types import Hook, HookContext, HookEvent, HookResult
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class TrajectoryHook(Hook):
    """Fire-and-forget: translates HookEvents → trajectory_manager calls."""

    name: str = "trajectory_hook"
    description: str = "Builds step-level training trajectories from agent lifecycle hooks."
    priority: int = 2

    async def handle(self, ctx: HookContext) -> HookResult:
        """Drive ``trajectory_manager`` through the current agent lifecycle event.

        Wraps the payload in a :class:`TrajectoryContext` and routes each event to
        the manager: ON_START begins a trajectory, POST_ACTION records an
        observation, POST_STEP closes the step, and ON_STOP finalizes it. Other
        events are ignored.

        Args:
            ctx: Hook context whose ``id`` is the session id and whose ``input``
                carries ``event``, ``task_id`` and ``agent_name``.

        Returns:
            Always ``HookResult.allow()`` (this hook only observes).
        """
        from autogenesis.trajectory.server import trajectory_manager
        from autogenesis.trajectory.types import TrajectoryContext

        inp = ctx.input
        if not inp:
            return HookResult.allow()

        event = inp.get("event")
        # Build the typed trajectory context: id=session (ctx.id), task_id=run id,
        # input carries the per-event payload the manager reads.
        tctx = TrajectoryContext(
            id=ctx.id,
            task_id=inp.get("task_id") or ctx.id,
            agent_name=inp.get("agent_name") or "",
            workspace_root=config.workspace_root,
            input=inp,
        )

        if event == HookEvent.ON_START:
            trajectory_manager.begin(tctx)
        elif event == HookEvent.POST_ACTION:
            trajectory_manager.add_observation(tctx)
        elif event == HookEvent.POST_STEP:
            trajectory_manager.close_step(tctx)
        elif event == HookEvent.ON_STOP:
            trajectory_manager.finalize(tctx)

        return HookResult.allow()
