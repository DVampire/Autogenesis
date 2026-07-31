"""StepConstraint — limits the number of steps an agent may take."""

from typing import Any, Dict

from pydantic import Field

from autogenesis.constraint.types import Constraint, ConstraintContext, ConstraintStatus
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import CONSTRAINT

@CONSTRAINT.register_module()
class StepConstraint(Constraint):
    """Hard cap on the number of think-and-act steps.

    The cap may be overridden per call via ``input["max_step"]``.
    """

    name: str = Field(default="step_constraint")
    description: str = Field(default="Hard cap on the number of think-and-act steps an agent may take.")
    max_step: int = Field(default=30, description="Default maximum number of steps allowed.")

    async def __call__(self, input: Dict[str, Any], ctx: ConstraintContext) -> Response:
        max_step = self._effective_limit(ctx.id, input, "max_step", self.max_step)
        state = self._state[ctx.id]
        state["step"] = state.get("step", 0) + 1

        data = {
            "status": ConstraintStatus(
                name=self.name,
                used=state["step"],
                limit=max_step,
                unit="steps",
            ).model_dump(),
        }

        if state["step"] > max_step:
            return Response(
                type=ResponseType.CONSTRAINT,
                success=False,
                message=f"Step limit reached ({state['step']}/{max_step})",
                data=data,
            )
        return Response(type=ResponseType.CONSTRAINT,
                        success=True,
                        message=f"Current step is [{state['step']}/{max_step}] within limit.",
                        data=data
                        )
