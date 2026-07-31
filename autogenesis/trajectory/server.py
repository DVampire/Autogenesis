"""TrajectoryManagerServer — accumulates step-level trajectories from hook events.

Parallels TraceManager/MemoryManagerServer: owns the global ``trajectory_manager``
singleton. A run builds up in memory keyed by ``task_id`` (fed by
``TrajectoryHook`` from the agent lifecycle), is persisted as JSONL on
``finalize``, and can be reward-backfilled afterwards via ``set_reward``
(rewards typically arrive after the agent returns — e.g. from a benchmark judge).

Persistence: ``<log_root>/trajectory/<task_id>.jsonl`` — line 1 is the trajectory
header (metadata), the remaining lines are one serialized step each.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from autogenesis.logger import logger
from autogenesis.trajectory.types import Trajectory, TrajectoryContext, TrajectoryStep


class TrajectoryManagerServer:
    """Singleton server that builds, persists, and exports agent trajectories."""

    def __init__(self) -> None:
        self.base_dir: Optional[str] = None
        # task_id → trajectory being built / finalized (retained for reward backfill)
        self._trajectories: Dict[str, Trajectory] = {}
        # task_id → the step currently open (lazily created on first observation)
        self._open_steps: Dict[str, TrajectoryStep] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        from autogenesis.config import config
        from autogenesis.utils import assemble_workspace_path

        try:
            log_root = config.log_root
        except (AttributeError, KeyError):
            # config not initialized (e.g. isolated tests) — fall back to workspace_root.
            log_root = "workspace_root"
        self.base_dir = assemble_workspace_path(os.path.join(log_root, "trajectory"))
        logger.info(f"| 📁 Trajectory manager base directory: {self.base_dir}")

    def rebind(self, log_root: str) -> None:
        """Re-point persistence at ``<log_root>/trajectory`` for a newly bound session.

        Long-lived hosts (the Gateway) initialize this manager once, before any
        session exists; binding a session re-points it so trajectories land under
        that session's own log root.
        """
        from autogenesis.utils import assemble_workspace_path

        self.base_dir = assemble_workspace_path(os.path.join(log_root, "trajectory"))

    # ------------------------------------------------------------------
    # Build — driven by TrajectoryHook
    # ------------------------------------------------------------------

    def begin(self, ctx: TrajectoryContext) -> None:
        """ON_START — open a fresh trajectory for this run."""
        inp = ctx.input
        self._trajectories[ctx.task_id] = Trajectory(
            session_id=ctx.session_id,
            task_id=ctx.task_id,
            agent_name=ctx.agent_name,
            task_description=inp.get("task") or "",
            metadata={
                k: inp.get(k)
                for k in ("parent_session_id", "subtask_id")
                if inp.get(k)
            },
        )
        self._open_steps.pop(ctx.task_id, None)

    def _current_step(self, task_id: str, step_number: int) -> TrajectoryStep:
        """Return the open step for this task, creating it lazily if needed.

        Lazy creation means we don't depend on a PRE_STEP wiring: the first
        POST_ACTION (or POST_STEP) of a step materializes it.
        """
        step = self._open_steps.get(task_id)
        if step is None or step.step_number != step_number:
            step = TrajectoryStep(step_number=step_number)
            self._open_steps[task_id] = step
        return step

    def add_observation(self, ctx: TrajectoryContext) -> None:
        """POST_ACTION — record one action's result/error into the open step."""
        if ctx.task_id not in self._trajectories:
            return
        inp = ctx.input
        step = self._current_step(ctx.task_id, inp.get("step_number", 0))
        action = inp.get("action") or {}
        step.observations.append({
            "index": action.get("index"),
            "type": action.get("type"),
            "name": action.get("name"),
            "args": action.get("args"),
            "result": _stringify(inp.get("action_result")),
            "error": inp.get("error"),
        })

    def close_step(self, ctx: TrajectoryContext) -> None:
        """POST_STEP — attach the effective prompt + decision + tokens, then commit."""
        traj = self._trajectories.get(ctx.task_id)
        if traj is None:
            return
        inp = ctx.input
        step = self._current_step(ctx.task_id, inp.get("step_number", 0))
        step.messages_sent = inp.get("messages") or []
        step.reasoning = inp.get("reasoning") or ""
        step.actions = inp.get("plan") or []
        step.token_usage = inp.get("step_tokens") or 0
        traj.steps.append(step)
        self._open_steps.pop(ctx.task_id, None)

    def finalize(self, ctx: TrajectoryContext) -> None:
        """ON_STOP — mark outcome and persist. Reward may arrive later."""
        traj = self._trajectories.get(ctx.task_id)
        if traj is None:
            return
        inp = ctx.input
        traj.success = bool(inp.get("success", False))
        traj.final_result = _stringify(inp.get("result"))
        self._open_steps.pop(ctx.task_id, None)
        self._persist(traj)

    # ------------------------------------------------------------------
    # Reward — arrives after the run (benchmark judge / evaluator)
    # ------------------------------------------------------------------

    def set_reward(self, task_id: str, reward: float) -> None:
        """Backfill a task-level reward to every step and re-persist.

        The run's ``task_id`` is surfaced on ``Response.data["task_id"]`` so a
        driver that runs an agent and then scores its output can correlate the
        two.
        """
        traj = self._trajectories.get(task_id)
        if traj is None:
            logger.warning(f"| ⚠️ set_reward: no trajectory for task_id={task_id}")
            return
        traj.backfill_reward(reward)
        self._persist(traj)
        logger.info(f"| 🎯 Trajectory reward set: task_id={task_id} reward={reward}")

    def set_reward_by_session(self, session_id: str, reward: float) -> int:
        """Backfill reward to every trajectory in a session. Returns count matched.

        Convenience for the common one-task-per-session case (e.g. a benchmark
        that runs one agent session per task) where the caller holds the
        session id (``ctx.id``) rather than the run's task_id.
        """
        matched = [t for t in self._trajectories.values() if t.session_id == session_id]
        for traj in matched:
            traj.backfill_reward(reward)
            self._persist(traj)
        if not matched:
            logger.warning(f"| ⚠️ set_reward_by_session: no trajectory for session_id={session_id}")
        else:
            logger.info(f"| 🎯 Trajectory reward set: session_id={session_id} reward={reward} ({len(matched)})")
        return len(matched)

    # ------------------------------------------------------------------
    # Query / export
    # ------------------------------------------------------------------

    def get(self, task_id: str) -> Optional[Trajectory]:
        return self._trajectories.get(task_id)

    def export_sft(self, task_id: str) -> List[Dict[str, Any]]:
        traj = self._trajectories.get(task_id)
        return traj.to_sft_records() if traj else []

    def export_rl(self, task_id: str, fmt: Any) -> List[Dict[str, Any]]:
        traj = self._trajectories.get(task_id)
        return traj.to_rl_records(fmt) if traj else []

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _path(self, traj: Trajectory) -> str:
        base = self.base_dir or "."
        safe = traj.task_id.replace("/", "_").replace("\\", "_")
        return os.path.join(base, f"{safe}.jsonl")

    def _persist(self, traj: Trajectory) -> None:
        try:
            path = self._path(traj)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            d = traj.to_dict()
            steps = d.pop("steps")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"__header__": True, **d}, ensure_ascii=False) + "\n")
                for step in steps:
                    f.write(json.dumps(step, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"| ⚠️ Trajectory persist failed (task_id={traj.task_id}): {e}")


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


# Global singleton — import this everywhere
trajectory_manager = TrajectoryManagerServer()
