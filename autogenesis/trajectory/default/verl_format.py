"""VerlFormat — a minimal built-in RLFormat implementation.

Produces one episode record per step in a shape suitable for GRPO/PPO-style
training (prompt / response / reward). Token-level fields
(``prompt_ids`` / ``response_ids`` / ``response_mask``) are left empty here and
are meant to be filled by an RL model provider's ``annotate_trajectory`` hook,
which has access to the tokenizer — keeping the training-framework and
tokenizer dependencies out of the framework core.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autogenesis.trajectory.types import Trajectory


class VerlFormat:
    """Default RL episode serializer (text-level; token annotation added by provider)."""

    name: str = "verl"

    def to_episode(self, trajectory: Trajectory) -> List[Dict[str, Any]]:
        episodes: List[Dict[str, Any]] = []
        for step in trajectory.steps:
            record = step.to_sft_record()
            prompt_messages = record["messages"][:-1]      # everything but the assistant target
            response = record["messages"][-1]              # the assistant target (content + tool_calls)
            episodes.append({
                "prompt": prompt_messages,
                "response": response,
                "reward": step.reward,
                "step": step.step_number,
                "task_id": trajectory.task_id,
                "agent_name": trajectory.agent_name,
                # Token-level fields — populated by an RL provider's annotate_trajectory.
                "prompt_ids": [],
                "response_ids": [],
                "response_mask": [],
            })
        return episodes


__all__ = ["VerlFormat"]
