"""WallTimeConstraint — limits total wall-clock time per task."""

from datetime import datetime
from typing import Any, Dict

from pydantic import Field

from autogenesis.constraint.types import Constraint, ConstraintContext, ConstraintStatus
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import CONSTRAINT


@CONSTRAINT.register_module()
class WallTimeConstraint(Constraint):
    """Stops the agent when elapsed wall-clock time since the first step exceeds the cap.

    The cap may be overridden per call via ``input["max_second"]``.
    """

    name: str = Field(default="wall_time_constraint")
    description: str = Field(default="Stops the agent when elapsed wall-clock time since the first step exceeds the cap.")
    max_second: float = Field(default=300.0, description="Default maximum wall-clock seconds allowed.")

    async def __call__(self, input: Dict[str, Any], ctx: ConstraintContext) -> Response:
        max_second = self._effective_limit(ctx.id, input, "max_second", self.max_second)
        state = self._state[ctx.id]
        state.setdefault("start_time", datetime.now())
        elapsed = (datetime.now() - state["start_time"]).total_seconds()

        data = {
            "status": ConstraintStatus(
                name=self.name,
                used=elapsed,
                limit=max_second,
                unit="seconds",
            ).model_dump(),
        }

        if elapsed >= max_second:
            return Response(
                type=ResponseType.CONSTRAINT,
                success=False,
                message=f"Wall-time limit reached ({elapsed:.0f}s/{max_second:.0f}s)",
                data=data,
            )
        return Response(type=ResponseType.CONSTRAINT,
                        success=True,
                        message=f"Current elapsed [{elapsed:.0f}s/{max_second:.0f}s] within limit.",
                        data=data
                        )
